#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

import ipaddress
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

import ops
from lightkube import Client
from lightkube.core.exceptions import ApiError
from lightkube.generic_resource import create_namespaced_resource
from ops import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.main import main
from ops.manifests import Collector, Manifests
from tenacity import before_log, retry, retry_if_exception_type, stop_after_delay, wait_exponential

from metallb_manifests import MetallbNativeManifest

# Log messages can be retrieved using juju debug-log
logger = logging.getLogger(__name__)


def _missing_resources(manifest: Manifests):
    expected = manifest.resources
    installed = manifest.installed_resources()
    missing = expected - installed
    return missing


BaseAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
BaseNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


@dataclass
class IPRange:
    addresses: List[str]

    @staticmethod
    def _to_ip_address(test: str) -> BaseAddress | None:
        try:
            return ipaddress.ip_address(test)
        except ValueError:
            return None

    @staticmethod
    def _to_address_range(test: str) -> Tuple[BaseAddress, BaseAddress] | None:
        addresses = test.split("-")
        if len(addresses) != 2:
            return None

        addresses = [IPRange._to_ip_address(_) for _ in addresses]
        addresses = [_ for _ in addresses if _ is not None]
        if len(addresses) != 2:
            return None

        return tuple(addresses)

    @staticmethod
    def _to_cidr(str_to_test) -> BaseNetwork | None:
        try:
            return ipaddress.ip_network(str_to_test)
        except ValueError:
            return None

    @classmethod
    def parse(cls, iprange: str) -> Tuple[Optional["IPRange"], str]:
        if not iprange:
            return None, "iprange must not be empty"
        ranges = []
        items = iprange.split(",")
        for item in items:
            if ip_range := cls._to_address_range(item):
                ranges.append("-".join(map(str, ip_range)))
            elif cidr := cls._to_cidr(item):
                ranges.append(str(cidr))
            else:
                return None, f"{item} is not a valid CIDR or ip range"

        return cls(ranges), ""


class MetallbCharm(ops.CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        super().__init__(*args)
        if not self.unit.is_leader():
            self.unit.status = BlockedStatus("MetalLB charm cannot be scaled > n1.")
            logger.error(f"{self} was initialized without leadership.")
            return

        self.native_manifest = MetallbNativeManifest(self, self.config)
        self.native_collector = Collector(self.native_manifest)
        self.client = Client(namespace=self.model.name, field_manager=self.app.name)
        self.l2_adv_name = self.pool_name = f"{self.model.name}-{self.app.name}"

        # Create generic lightkube resource class for the MetalLB IPAddressPool
        # Create generic lightkube resource class for the MetalLB L2Advertisement
        # https://metallb.universe.tf/configuration/
        self.IPAddressPool = create_namespaced_resource(
            group="metallb.io",
            version="v1beta1",
            kind="IPAddressPool",
            plural="ipaddresspools",
        )

        self.L2Advertisement = create_namespaced_resource(
            group="metallb.io",
            version="v1beta1",
            kind="L2Advertisement",
            plural="l2advertisements",
        )

        self.framework.observe(self.on.install, self._install_or_upgrade)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.upgrade_charm, self._install_or_upgrade)
        self.framework.observe(self.on.update_status, self._update_status)
        self.framework.observe(self.on.remove, self._cleanup)

    def _confirm_resource(self, resource, name) -> bool:
        try:
            self.client.get(resource, name=name, namespace=self.config["namespace"])
        except ApiError as e:
            if "not found" in e.status.message:
                logger.info(f"{resource.__name__} not found yet")
                self.unit.status = WaitingStatus(f"Waiting for {resource.__name__} to be created")
                return False
            else:
                # surface any other errors besides not found
                logger.exception(e)
                self.unit.status = WaitingStatus("Waiting for Kubernetes API")
                return False
        return True

    def _update_status(self, _):
        missing = _missing_resources(self.native_manifest)
        if len(missing) != 0:
            logger.error(f"missing MetalLB resources: {missing}")
            self.unit.status = BlockedStatus(
                "missing \n".join(sorted(str(rsc) for rsc in missing))
            )
            return

        native_unready = self.native_collector.unready
        if native_unready:
            logger.warning(f"Unready MetalLB resources: {native_unready}")
            self.unit.status = WaitingStatus(", ".join(native_unready))
            return

        if not self._confirm_resource(self.IPAddressPool, self.pool_name):
            return
        if not self._confirm_resource(self.L2Advertisement, self.l2_adv_name):
            return

        self.unit.status = ActiveStatus("Ready")
        self.unit.set_workload_version(self.native_collector.short_version)
        self.app.status = ActiveStatus(self.native_collector.long_version)

    def _install_or_upgrade(self, event):
        logger.info("Installing MetalLB native manifest resources ...")
        self.native_manifest.apply_manifests()
        logger.info("MetalLB native manifest has been installed")

    def _cleanup(self, event):
        self.unit.status = MaintenanceStatus("Cleaning up MetalLB resources")
        self.native_manifest.delete_manifests(ignore_unauthorized=True, ignore_not_found=True)
        self.unit.status = MaintenanceStatus("Shutting down")

    def _on_config_changed(self, event):
        logger.info("Updating MetalLB IPAddressPool to reflect charm configuration")
        # strip all whitespace from string
        stripped = "".join(self.config["iprange"].split())
        iprange, err = IPRange.parse(stripped)
        if not iprange:
            err_msg = f"Invalid iprange: {err}"
            logger.error(err_msg)
            self.unit.status = BlockedStatus(err_msg)
            return

        self._update_ip_pool(iprange.addresses)
        self._update_l2_adv()
        self.unit.status = ActiveStatus()

    # retrying is necessary as the ip address pool webhooks take some time to come up
    @retry(
        retry=retry_if_exception_type(ApiError),
        reraise=True,
        before=before_log(logger, logging.DEBUG),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        stop=stop_after_delay(60 * 5),
    )
    def _update_ip_pool(self, addresses):
        ip_pool = self.IPAddressPool(
            metadata={"name": self.pool_name, "namespace": self.config["namespace"]},
            spec={"addresses": addresses},
        )

        self.client.apply(ip_pool, force=True)

    def _update_l2_adv(self):
        l2_adv = self.L2Advertisement(
            metadata={"name": self.l2_adv_name, "namespace": self.config["namespace"]},
            spec={"ipAddressPools": [self.pool_name]},
        )

        self.client.apply(l2_adv, force=True)


if __name__ == "__main__":  # pragma: nocover
    main(MetallbCharm)
