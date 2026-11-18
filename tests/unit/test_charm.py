# Copyright 2023 Stone
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest.mock as mock
from pathlib import Path

import ops
import ops.testing
import pytest
import yaml
from lightkube.core.exceptions import ApiError
from lightkube.generic_resource import get_generic_resource
from ops import ActiveStatus, BlockedStatus, WaitingStatus
from ops.testing import Harness

from charm import MetallbCharm
from metallb_manifests import MetallbNativeManifest

ops.testing.SIMULATE_CAN_CONNECT = True


@pytest.fixture
def harness():
    harness = Harness(MetallbCharm)
    try:
        yield harness
    finally:
        harness.cleanup()


def test_not_leader(harness):
    harness.begin()
    assert harness.charm.model.unit.status == BlockedStatus("MetalLB charm cannot be scaled > n1.")


@pytest.mark.parametrize(
    "release",
    [None] + sorted(path.name for path in Path("upstream/metallb-native/manifests").iterdir()),
)
def test_install_applies_manifest_objects(harness, lk_manifests_client, release):
    # Test that the install-handler applies the objects specified in the manifest
    lk_manifests_client.reset_mock()
    if release is not None:
        harness.update_config({"metallb-release": release})
    harness.set_leader(True)
    harness.begin()
    harness.charm.on.install.emit()

    version = harness.charm.config["metallb-release"]
    file_name = f"upstream/metallb-native/manifests/{version}/metallb-native.yaml"
    expected_objects = list(yaml.safe_load_all(open(file_name)))

    # the apply method is called for every object in the manifest
    for call in lk_manifests_client.apply.call_args_list:
        # The first (and only) argument to the apply method is the obj
        call_obj = call.args[0].to_dict()
        # look for this object in the manifest by name
        # the manifest objects are manipulated slightly (image registries changed, labels added, etc)
        # so it won't be an EXACT match, but each object should still be accounted for
        found = False
        for obj in expected_objects:
            if obj["metadata"]["name"] == call_obj["metadata"]["name"]:
                found = True
        assert found


def _applied_releases(lk_manifests_client):
    """Collect the manifest-version labels of every applied manifest resource."""
    return {
        call.args[0].metadata.labels["juju.io/manifest-version"]
        for call in lk_manifests_client.apply.call_args_list
    }


def test_refresh_rolls_out_schema_default(harness, lk_manifests_client):
    """A charm refresh must re-apply the manifests at the new schema default.

    The default release is defined by `config.yaml` and `upstream/metallb-native/version`.
    Simulate an installation pinned to the previous default, then refresh with the
    release option unset so that the schema default applies.
    """
    previous_default = "v0.13.10"
    new_default = yaml.safe_load(Path("config.yaml").read_text())["options"]["metallb-release"][
        "default"
    ]
    assert new_default == Path("upstream/metallb-native/version").read_text().strip()
    assert new_default != previous_default

    harness.update_config({"metallb-release": previous_default})
    harness.set_leader(True)
    harness.begin()
    harness.charm.on.install.emit()
    assert _applied_releases(lk_manifests_client) == {f"metallb-{previous_default}"}

    # Refreshing the charm clears the explicitly pinned release, so the schema
    # default must take effect and be rolled out.
    lk_manifests_client.reset_mock()
    harness.update_config(unset=["metallb-release"])
    harness.charm.on.upgrade_charm.emit()
    assert _applied_releases(lk_manifests_client) == {f"metallb-{new_default}"}


def _api_error(code):
    api_error = ApiError(response=mock.MagicMock())
    api_error.status.code = code
    api_error.status.message = "not found"
    return api_error


def _legacy_pool(name="legacy-pool"):
    pool = mock.MagicMock()
    pool.metadata.name = name
    return pool


def _set_deployed_release(lk_charm_client, release):
    """Make the controller Deployment look as applied by the given release, or absent."""
    if release is None:
        lk_charm_client.get.side_effect = _api_error(404)
        return
    controller = mock.MagicMock()
    controller.metadata.labels = {"juju.io/manifest-version": f"metallb-{release}"}
    lk_charm_client.get.side_effect = None
    lk_charm_client.get.return_value = controller


@pytest.mark.parametrize("event", ["install", "upgrade_charm", "config_changed"])
def test_legacy_address_pools_block_unsupported_release(
    harness, lk_manifests_client, lk_charm_client, event
):
    """Releases without the AddressPool API must not be applied while pools exist."""
    lk_charm_client.list.return_value = [_legacy_pool()]
    _set_deployed_release(lk_charm_client, "v0.13.10")

    harness.set_leader(True)
    harness.begin()
    getattr(harness.charm.on, event).emit()

    status = harness.charm.model.unit.status
    assert isinstance(status, BlockedStatus)
    assert "legacy-pool" in status.message
    assert "kubectl get addresspools.metallb.io -n metallb-system -o yaml" in status.message
    assert "kubectl delete addresspools.metallb.io <name> -n metallb-system" in status.message
    assert lk_manifests_client.apply.call_args_list == []
    assert lk_charm_client.delete.call_args_list == []


def test_legacy_address_pools_unblock_on_update_status(
    harness, lk_manifests_client, lk_charm_client
):
    """Once the user has migrated the objects, update-status applies the release."""
    lk_charm_client.list.return_value = [_legacy_pool()]
    _set_deployed_release(lk_charm_client, "v0.13.10")

    harness.set_leader(True)
    harness.begin()
    harness.charm.on.upgrade_charm.emit()
    assert isinstance(harness.charm.model.unit.status, BlockedStatus)

    # still present: nothing applied, still blocked
    harness.charm.on.update_status.emit()
    assert isinstance(harness.charm.model.unit.status, BlockedStatus)
    assert lk_manifests_client.apply.call_args_list == []

    # the user migrated the objects
    lk_charm_client.list.return_value = []
    harness.charm.on.update_status.emit()
    assert not isinstance(harness.charm.model.unit.status, BlockedStatus)
    assert _applied_releases(lk_manifests_client) == {"metallb-v0.16.2"}
    applied_kinds = {type(call.args[0]).__name__ for call in lk_charm_client.apply.call_args_list}
    assert applied_kinds == {"IPAddressPool", "L2Advertisement"}
    assert lk_charm_client.delete.call_args_list == []


def test_no_address_pools_never_blocks(harness, lk_manifests_client, lk_charm_client):
    """Users without AddressPool objects are not blocked and pay for no extra API calls."""
    lk_charm_client.list.return_value = []

    harness.set_leader(True)
    harness.begin()
    for event in (harness.charm.on.install, harness.charm.on.config_changed):
        event.emit()
        assert not isinstance(harness.charm.model.unit.status, BlockedStatus)
    assert _applied_releases(lk_manifests_client) == {"metallb-v0.16.2"}

    lk_charm_client.list.reset_mock()
    harness.charm.on.update_status.emit()
    assert not isinstance(harness.charm.model.unit.status, BlockedStatus)
    assert lk_charm_client.list.call_args_list == []


def test_legacy_address_pools_allowed_on_serving_release(
    harness, lk_manifests_client, lk_charm_client
):
    """A release which still serves AddressPool keeps working with existing pools."""
    lk_charm_client.list.return_value = [_legacy_pool()]

    harness.update_config({"metallb-release": "v0.13.10"})
    harness.set_leader(True)
    harness.begin()
    harness.charm.on.install.emit()

    assert _applied_releases(lk_manifests_client) == {"metallb-v0.13.10"}
    assert lk_charm_client.delete.call_args_list == []


@pytest.mark.parametrize("deployed", ["v0.14.9", "v0.15.3", "v0.16.2"])
def test_legacy_address_pools_do_not_block_when_already_unsupported(
    harness, lk_manifests_client, lk_charm_client, deployed
):
    """Leftover AddressPool objects are inert once the cluster runs a release without them.

    The charm never prunes the legacy CRD, so objects created or left after the upgrade
    must not block later config changes (e.g. iprange) on an otherwise healthy cluster.
    """
    lk_charm_client.list.return_value = [_legacy_pool()]
    _set_deployed_release(lk_charm_client, deployed)

    harness.set_leader(True)
    harness.begin()
    harness.charm.on.config_changed.emit()

    assert not isinstance(harness.charm.model.unit.status, BlockedStatus)
    assert _applied_releases(lk_manifests_client) == {"metallb-v0.16.2"}


def test_missing_legacy_crd_does_not_block(harness, lk_manifests_client, lk_charm_client):
    """An absent AddressPool CRD means there is nothing to migrate."""
    lk_charm_client.list.side_effect = _api_error(404)

    harness.set_leader(True)
    harness.begin()
    harness.charm.on.install.emit()

    assert _applied_releases(lk_manifests_client) == {"metallb-v0.16.2"}


@pytest.mark.parametrize(
    "release", sorted(path.name for path in Path("upstream/metallb-native/manifests").iterdir())
)
def test_native_bundle_custom_configuration(
    harness, lk_manifests_client, lk_charm_client, release
):
    namespace = "custom-metallb"
    registry = "registry.example.test/mirror"
    selector = {"kubernetes.io/os": "linux", "kubernetes.io/arch": "amd64"}
    harness.update_config(
        {
            "metallb-release": release,
            "namespace": namespace,
            "image-registry": registry,
            "node-selector": "kubernetes.io/os=linux kubernetes.io/arch=amd64",
        }
    )
    harness.set_leader(True)
    harness.begin()
    harness.charm.on.config_changed.emit()

    objects = [call.args[0].to_dict() for call in lk_manifests_client.apply.call_args_list]
    services = {obj["metadata"]["name"] for obj in objects if obj["kind"] == "Service"}
    crds = {}
    for obj in objects:
        if obj["metadata"].get("namespace"):
            assert obj["metadata"]["namespace"] == namespace
        if obj["kind"] == "Namespace":
            assert obj["metadata"]["name"] == namespace
        if obj["kind"] in ("RoleBinding", "ClusterRoleBinding"):
            assert all(subject["namespace"] == namespace for subject in obj["subjects"])
        if obj["kind"] == "CustomResourceDefinition":
            crds[obj["spec"]["names"]["kind"]] = obj
            conversion = obj["spec"].get("conversion", {})
            if conversion.get("strategy") == "Webhook":
                service = conversion["webhook"]["clientConfig"]["service"]
                assert service["namespace"] == namespace
                assert service["name"] in services
        if obj["kind"] == "ValidatingWebhookConfiguration":
            for webhook in obj["webhooks"]:
                service = webhook["clientConfig"]["service"]
                assert service["namespace"] == namespace
                assert service["name"] in services
                assert webhook["failurePolicy"] == "Fail"
        if obj["kind"] in ("Deployment", "DaemonSet"):
            pod = obj["spec"]["template"]["spec"]
            assert pod["nodeSelector"] == selector
            assert len(pod["containers"]) == 1  # Native bundle, not FRR sidecars.
            container = pod["containers"][0]
            assert container["image"].startswith(f"{registry}/metallb/")
            assert all(
                env.get("value", "native") == "native"
                for env in container.get("env", [])
                if env["name"] == "METALLB_BGP_TYPE"
            )

    for call in lk_charm_client.apply.call_args_list:
        resource = call.args[0]
        kind = type(resource).__name__
        assert resource.metadata.namespace == namespace
        assert any(
            version["served"]
            and get_generic_resource(f"metallb.io/{version['name']}", kind) is type(resource)
            for version in crds[kind]["spec"]["versions"]
        )


def test_config_change_updates_ip_pool(harness, lk_charm_client):
    lk_charm_client.reset_mock()

    harness.set_leader(True)
    harness.begin()

    # test with single ip range
    harness.update_config({"iprange": "10.1.240.240-10.1.240.241"})
    assert len(lk_charm_client.apply.call_args_list) == 2
    apply_ip_pool_call = lk_charm_client.apply.call_args_list[0]
    apply_l2_adv_call = lk_charm_client.apply.call_args_list[1]

    call_obj = apply_ip_pool_call.args[0].to_dict()
    assert len(call_obj["spec"]["addresses"]) == 1
    assert call_obj["spec"]["addresses"][0] == "10.1.240.240-10.1.240.241"

    call_obj = apply_l2_adv_call.args[0].to_dict()
    assert len(call_obj["spec"]["ipAddressPools"]) == 1
    assert call_obj["spec"]["ipAddressPools"][0] == "None-metallb"

    # test with multiple ranges
    lk_charm_client.reset_mock()
    harness.update_config(
        {
            "iprange": "192.168.1.240-192.168.1.247,10.1.240.240-10.1.240.241,192.168.10.0/24,fc00:f853:0ccd:e799::/124"
        }
    )
    assert len(lk_charm_client.apply.call_args_list) == 2
    apply_ip_pool_call = lk_charm_client.apply.call_args_list[0]
    call_obj = apply_ip_pool_call.args[0].to_dict()
    assert len(call_obj["spec"]["addresses"]) == 4
    assert call_obj["spec"]["addresses"][0] == "192.168.1.240-192.168.1.247"
    assert call_obj["spec"]["addresses"][1] == "10.1.240.240-10.1.240.241"
    assert call_obj["spec"]["addresses"][2] == "192.168.10.0/24"
    assert call_obj["spec"]["addresses"][3] == "fc00:f853:0ccd:e799::/124"

    # test with multiple ranges with spaces thrown in
    lk_charm_client.reset_mock()
    harness.update_config(
        {
            "iprange": "  192. 168.1.240-192. 168.1.247, 10.1.240.240 -10.1.240.241,   192.168.10.0/24,fc00:f853:0ccd:e799::/124   "
        }
    )
    assert len(lk_charm_client.apply.call_args_list) == 2
    apply_ip_pool_call = lk_charm_client.apply.call_args_list[0]
    call_obj = apply_ip_pool_call.args[0].to_dict()
    assert len(call_obj["spec"]["addresses"]) == 4
    assert call_obj["spec"]["addresses"][0] == "192.168.1.240-192.168.1.247"
    assert call_obj["spec"]["addresses"][1] == "10.1.240.240-10.1.240.241"
    assert call_obj["spec"]["addresses"][2] == "192.168.10.0/24"
    assert call_obj["spec"]["addresses"][3] == "fc00:f853:0ccd:e799::/124"

    # test with an empty range
    lk_charm_client.reset_mock()
    harness.update_config({"iprange": ""})
    assert harness.charm.model.unit.status == BlockedStatus(
        "Invalid iprange: iprange must not be empty"
    )

    # test with an invalid range
    lk_charm_client.reset_mock()
    harness.update_config({"iprange": "256.256.256.256-256.256.256.256,10.1.240.240-10.1.240.241"})
    assert harness.charm.model.unit.status == BlockedStatus(
        "Invalid iprange: 256.256.256.256-256.256.256.256 is not a valid CIDR or ip range"
    )

    # test with an invalid separator in range
    lk_charm_client.reset_mock()
    harness.update_config({"iprange": "10.1.240.240+10.1.240.241"})
    assert harness.charm.model.unit.status == BlockedStatus(
        "Invalid iprange: 10.1.240.240+10.1.240.241 is not a valid CIDR or ip range"
    )

    # test with an invalid CIDR
    lk_charm_client.reset_mock()
    harness.update_config({"iprange": "256.256.256.256/24"})
    assert harness.charm.model.unit.status == BlockedStatus(
        "Invalid iprange: 256.256.256.256/24 is not a valid CIDR or ip range"
    )

    # test with an address without the cidr range is invalid
    lk_charm_client.reset_mock()
    harness.update_config({"iprange": "192.168.1.2"})
    assert harness.charm.model.unit.status == BlockedStatus(
        "Invalid iprange: 192.168.1.2 is not a valid CIDR or ip range"
    )


def test_remove_deletes_manifest_objects(harness, lk_manifests_client):
    # Test that the remove-handler deletes the objects specified in the manifest
    lk_manifests_client.reset_mock()
    harness.set_leader(True)
    harness.begin()
    harness.charm.on.remove.emit()

    version = harness.charm.config["metallb-release"]
    file_name = f"upstream/metallb-native/manifests/{version}/metallb-native.yaml"
    actual_kind_name_list = []
    expected_objects = list(yaml.safe_load_all(open(file_name)))
    expected_kind_name_list = []
    for obj in expected_objects:
        kind_name = {"kind": obj["kind"], "name": obj["metadata"]["name"]}
        expected_kind_name_list.append(kind_name)

    for call in lk_manifests_client.return_value.delete.call_args_list:
        # The first argument is the resource class
        # The second argument is the object name
        kind_name = {"kind": call.args[0].__name__, "name": call.args[1]}
        actual_kind_name_list.append(kind_name)


def test_update_status(harness, lk_manifests_client, lk_charm_client):
    lk_manifests_client.reset_mock()
    harness.set_leader(True)
    harness.begin()

    # With nothing mocked, all resources will appear as missing
    harness.charm._stored.configured = True
    harness.charm.model.unit.status = expected = BlockedStatus("TeSt BlOcKeD MeSsAgE")
    harness.charm.on.update_status.emit()
    assert harness.charm.model.unit.status == expected

    # mock to get past missing resources code path
    with mock.patch("charm._missing_resources", autospec=True) as mock_missing:
        mock_missing.return_value = []
        # Test path where some resources are not ready
        with mock.patch.object(harness.charm, "native_collector") as mock_collector:
            mock_collector.unready = [
                "some_name: some_obj is not Ready",
                "other_name: other_obj is not Ready",
            ]
            harness.charm.on.update_status.emit()
            assert harness.charm.model.unit.status == WaitingStatus(
                "some_name: some_obj is not Ready, other_name: other_obj is not Ready"
            )

        # test path where APIError occurs during IP Address Pool lookup
        # test path where ip address pool is not found
        lk_charm_client.reset_mock()
        api_error = ApiError(response=mock.MagicMock())
        api_error.status.message = "not found"
        lk_charm_client.get.side_effect = api_error
        harness.charm.on.update_status.emit()
        assert harness.charm.model.unit.status == WaitingStatus(
            "Waiting for IPAddressPool to be created"
        )

        # test path where some other API error occurs
        api_error.status.message = "something else happened"
        lk_charm_client.get.side_effect = api_error
        harness.charm.on.update_status.emit()
        assert harness.charm.model.unit.status == WaitingStatus("Waiting for Kubernetes API")

        # test ready path
        lk_charm_client.get.side_effect = None
        harness.charm.on.update_status.emit()
        assert harness.charm.model.unit.status == ActiveStatus("Ready")


def test_empty_config_option_not_used_by_manifest(harness):
    # Not super important, but can't get 100% coverage without it
    harness.update_config({"iprange": ""})
    harness.begin()
    manifest = MetallbNativeManifest(harness.charm, harness.charm.config)
    assert "iprange" not in manifest.config
