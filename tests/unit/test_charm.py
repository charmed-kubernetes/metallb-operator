# Copyright 2023 Stone
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest.mock as mock

import ops
import ops.testing
import pytest
import yaml
from lightkube.core.exceptions import ApiError
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


def test_install_applies_manifest_objects(harness, lk_manifests_client):
    # Test that the install-handler applies the objects specified in the manifest
    lk_manifests_client.reset_mock()
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


def test_config_change_updates_ip_pool(harness, lk_charm_client):
    lk_charm_client.reset_mock()

    harness.set_leader(True)
    harness.begin()

    # test with single ip range
    harness.update_config({"iprange": "10.1.240.240-10.1.240.241"})
    harness.charm.on.config_changed.emit()
    for call in lk_charm_client.apply.call_args_list:
        call_obj = call.args[0].to_dict()
        assert len(call_obj["spec"]["addresses"]) == 1
        assert call_obj["spec"]["addresses"][0] == "10.1.240.240-10.1.240.241"

    # test with multiple ranges
    lk_charm_client.reset_mock()
    harness.update_config(
        {
            "iprange": "192.168.1.240-192.168.1.247,10.1.240.240-10.1.240.241,192.168.10.0/24,fc00:f853:0ccd:e799::/124"
        }
    )
    harness.charm.on.config_changed.emit()
    for call in lk_charm_client.apply.call_args_list:
        call_obj = call.args[0].to_dict()
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
    harness.charm.on.config_changed.emit()
    for call in lk_charm_client.apply.call_args_list:
        call_obj = call.args[0].to_dict()
        assert len(call_obj["spec"]["addresses"]) == 4
        assert call_obj["spec"]["addresses"][0] == "192.168.1.240-192.168.1.247"
        assert call_obj["spec"]["addresses"][1] == "10.1.240.240-10.1.240.241"
        assert call_obj["spec"]["addresses"][2] == "192.168.10.0/24"
        assert call_obj["spec"]["addresses"][3] == "fc00:f853:0ccd:e799::/124"

    # test with an empty range
    lk_charm_client.reset_mock()
    harness.update_config({"iprange": ""})
    harness.charm.on.config_changed.emit()
    assert harness.charm.model.unit.status == BlockedStatus(
        "Invalid iprange: iprange must not be empty"
    )

    # test with an invalid range
    lk_charm_client.reset_mock()
    harness.update_config({"iprange": "256.256.256.256-256.256.256.256,10.1.240.240-10.1.240.241"})
    harness.charm.on.config_changed.emit()
    assert harness.charm.model.unit.status == BlockedStatus(
        "Invalid iprange: 256.256.256.256-256.256.256.256 is not a valid CIDR or ip range"
    )

    # test with an invalid separator in range
    lk_charm_client.reset_mock()
    harness.update_config({"iprange": "10.1.240.240+10.1.240.241"})
    harness.charm.on.config_changed.emit()
    assert harness.charm.model.unit.status == BlockedStatus(
        "Invalid iprange: 10.1.240.240+10.1.240.241 is not a valid CIDR or ip range"
    )

    # test with an invalid CIDR
    lk_charm_client.reset_mock()
    harness.update_config({"iprange": "256.256.256.256/24"})
    harness.charm.on.config_changed.emit()
    assert harness.charm.model.unit.status == BlockedStatus(
        "Invalid iprange: 256.256.256.256/24 is not a valid CIDR or ip range"
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
    harness.charm.on.update_status.emit()
    assert "missing" in harness.charm.model.unit.status.message
    assert harness.charm.model.unit.status.name == "blocked"

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
        assert harness.charm.model.unit.status == WaitingStatus(
            "Waiting for Kubernetes API"
        )

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
