#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

import contextlib
import ipaddress
import logging

import ops
from lightkube import Client
from lightkube.core.exceptions import ApiError
from lightkube.generic_resource import create_namespaced_resource
from ops import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.main import main
from ops.manifests import Collector, ManifestClientError, Manifests
from tenacity import before_log, retry, retry_if_exception_type, stop_after_delay, wait_exponential

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
    if str_to_test.count("/") != 1:
        return False
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


@contextlib.contextmanager
def _block_on_forbidden(unit: ops.model.Unit):
    try:
        yield
    except (ApiError, ManifestClientError) as ex:
        http = ex.args[1] if isinstance(ex, ManifestClientError) else ex
        if http.status.code == 403:
            unit.status = BlockedStatus("API Access Forbidden, deploy with --trust")
        else:
            raise


class MetallbCharm(ops.CharmBase):
    """Charm the service."""

    _stored = ops.StoredState()

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
        self.framework.observe(self.on.upgrade_charm, self._install_or_upgrade)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.update_status, self._update_status)
        self.framework.observe(self.on.remove, self._cleanup)
        self._stored.set_default(configured=False)

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
        if not self._stored.configured:
            logger.info("Waiting for configuration to be applied")
            return

        missing = _missing_resources(self.native_manifest)
        if len(missing) != 0:
            logger.error("missing MetalLB resources: %s", missing)
            return

        native_unready = self.native_collector.unready
        if native_unready:
            logger.warning("Unready MetalLB resources: %s", native_unready)
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
        with _block_on_forbidden(self.unit):
            self.native_manifest.apply_manifests()
            self.unit.status = WaitingStatus("Waiting for MetalLB resources to be configured")
            logger.info("MetalLB native manifest has been installed")

    def _cleanup(self, event):
        self.unit.status = MaintenanceStatus("Cleaning up MetalLB resources")
        with _block_on_forbidden(self.unit):
            self.native_manifest.delete_manifests(ignore_unauthorized=True, ignore_not_found=True)
            self.unit.status = MaintenanceStatus("Shutting down")

    def _on_config_changed(self, event):
        logger.info("Updating MetalLB IPAddressPool to reflect charm configuration")
        self._stored.configured = False
        # strip all whitespace from string
        stripped = "".join(self.config["iprange"].split())
        valid_iprange, msg = validate_iprange(stripped)
        if not valid_iprange:
            err_msg = f"Invalid iprange: {msg}"
            logger.error(err_msg)
            self.unit.status = BlockedStatus(err_msg)
            return

        addresses = stripped.split(",")
        with _block_on_forbidden(self.unit):
            self.unit.status = MaintenanceStatus("Updating Manifests")
            self.native_manifest.apply_manifests()
            self.unit.status = MaintenanceStatus("Updating Configuration")
            self._update_ip_pool(addresses)
            self._update_l2_adv()
            self._stored.configured = True
            self._update_status(event)

    # retrying is necessary as the ip address pool webhooks take some time to come up
    @retry(
        retry=retry_if_exception_type(ApiError),
        stop=stop_after_delay(60 * 5),
        reraise=True,
        before=before_log(logger, logging.WARNING),
        wait=wait_exponential(multiplier=1, min=2, max=60 * 2),
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
