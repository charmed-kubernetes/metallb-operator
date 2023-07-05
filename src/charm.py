#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

import ipaddress
import logging

import ops
from lightkube import Client
from lightkube.core.exceptions import ApiError
from lightkube.generic_resource import create_namespaced_resource
from ops import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.main import main
from ops.manifests import Collector, Manifests
from tenacity import before_log, retry, retry_if_exception_type, wait_exponential

from metallb_manifests import MetallbNativeManifest

# Log messages can be retrieved using juju debug-log
logger = logging.getLogger(__name__)


def _missing_resources(manifest: Manifests):
    expected = manifest.resources
    installed = manifest.installed_resources()
    missing = expected - installed
    return missing


def _is_ip_address(str_to_test):
    try:
        ipaddress.ip_address(str_to_test)
        return True
    except ValueError:
        return False


def _is_ip_address_range(str_to_test):
    addresses = str_to_test.split("-")
    if len(addresses) != 2:
        return False

    for address in addresses:
        if not _is_ip_address(address):
            return False

    return True


def _is_cidr(str_to_test):
    try:
        ipaddress.ip_network(str_to_test)
        return True
    except ValueError:
        return False


def validate_iprange(iprange):
    if not iprange:
        return False, "iprange must not be empty"

    items = iprange.split(",")
    for item in items:
        is_ip_range = _is_ip_address_range(item)
        is_cidr = _is_cidr(item)
        if not is_ip_range and not is_cidr:
            return False, f"{item} is not a valid CIDR or ip range"

    return True, ""


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
        self.pool_name = f"{self.model.name}-{self.app.name}"
        # Create generic lightkube resource class for the MetalLB IPAddressPool
        # https://metallb.universe.tf/configuration/
        self.IPAddressPool = create_namespaced_resource(
            group="metallb.io",
            version="v1beta1",
            kind="IPAddressPool",
            plural="ipaddresspools",
        )

        self.framework.observe(self.on.install, self._install_or_upgrade)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.upgrade_charm, self._install_or_upgrade)
        self.framework.observe(self.on.update_status, self._update_status)
        self.framework.observe(self.on.remove, self._cleanup)

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

        try:
            self.client.get(
                self.IPAddressPool, name=self.pool_name, namespace=self.config["namespace"]
            )
        except ApiError as e:
            if "not found" in e.status.message:
                logger.info("IPAddressPool not found yet")
                self.unit.status = WaitingStatus("Waiting for IPAddressPool to be created")
                return
            else:
                # surface any other errors besides not found
                logger.exception(e)
                self.unit.status = WaitingStatus("Waiting for Kubernetes API")
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
        valid_iprange, msg = validate_iprange(stripped)
        if not valid_iprange:
            err_msg = f"Invalid iprange: {msg}"
            logger.error(err_msg)
            self.unit.status = BlockedStatus(err_msg)
            return

        addresses = stripped.split(",")
        self._update_ip_pool(addresses)
        self.unit.status = ActiveStatus()

    # retrying is necessary as the ip address pool webhooks take some time to come up
    @retry(
        retry=retry_if_exception_type(ApiError),
        reraise=True,
        before=before_log(logger, logging.INFO),
        wait=wait_exponential(multiplier=1, min=2, max=60 * 2),
    )
    def _update_ip_pool(self, addresses):
        ip_pool = self.IPAddressPool(
            metadata={"name": self.pool_name, "namespace": self.config["namespace"]},
            spec={"addresses": addresses},
        )

        self.client.apply(ip_pool, force=True)


if __name__ == "__main__":  # pragma: nocover
    main(MetallbCharm)
