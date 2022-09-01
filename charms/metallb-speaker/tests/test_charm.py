"""Unit tests."""

import unittest
from unittest.mock import Mock, patch

from charm import MetalLBSpeakerCharm

from ops.testing import Harness

from utils import get_pod_spec


class TestCharm(unittest.TestCase):
    """MetalLB Controller Charm Unit Tests."""

    @patch.dict("charm.os.environ", {"JUJU_MODEL_NAME": "unit-test-metallb"})
    def setUp(self):
        """Test setup."""
        self.harness = Harness(MetalLBSpeakerCharm)
        self.harness.set_leader(is_leader=True)
        self.harness.begin()

    @patch.dict("charm.os.environ", {"JUJU_MODEL_NAME": "unit-test-metallb"})
    @patch("utils.create_namespaced_role_binding_with_api")
    @patch("utils.create_namespaced_role_with_api")
    @patch("utils.create_pod_security_policy_with_api")
    @patch("utils.get_k8s_version")
    def test_on_start_lt_1_25(
        self, get_k8s_version, create_psp, create_ns_role, create_ns_role_binding
    ):
        """Test installation < 1.25.0."""
        get_k8s_version.return_value = (1, 24, 6)
        mock_pod_spec = self.harness.charm.set_pod_spec = Mock()
        self.assertFalse(self.harness.charm._stored.started)
        self.harness.charm.on.start.emit()
        mock_pod_spec.assert_called_once()
        create_psp.assert_called_once()
        self.assertEqual(create_ns_role.call_count, 2)
        self.assertEqual(create_ns_role_binding.call_count, 2)
        self.assertTrue(self.harness.charm._stored.started)

    @patch.dict("charm.os.environ", {"JUJU_MODEL_NAME": "unit-test-metallb"})
    @patch("utils.create_namespaced_role_binding_with_api")
    @patch("utils.create_namespaced_role_with_api")
    @patch("utils.create_pod_security_policy_with_api")
    @patch("utils.get_k8s_version")
    def test_on_start_gte_1_25(
        self, get_k8s_version, create_psp, create_ns_role, create_ns_role_binding
    ):
        """Test installation >= 1.2.50."""
        get_k8s_version.return_value = (1, 25, 0)
        mock_pod_spec = self.harness.charm.set_pod_spec = Mock()
        self.assertFalse(self.harness.charm._stored.started)
        self.harness.charm.on.start.emit()
        mock_pod_spec.assert_called_once()
        create_psp.assert_not_called()
        self.assertEqual(create_ns_role.call_count, 2)
        self.assertEqual(create_ns_role_binding.call_count, 2)
        self.assertTrue(self.harness.charm._stored.started)

    @patch("utils.delete_namespaced_role_with_api")
    @patch("utils.delete_namespaced_role_binding_with_api")
    @patch("utils.delete_pod_security_policy_with_api")
    @patch("utils.get_k8s_version")
    def test_on_remove_lt_1_25(
        self, get_k8s_version, delete_psp, delete_ns_role_binding, delete_ns_role
    ):
        """Test remove hook < 1.25.0."""
        get_k8s_version.return_value = (1, 24, 6)
        self.harness.charm.on.remove.emit()
        delete_psp.assert_called_once()
        self.assertEqual(delete_ns_role.call_count, 2)
        self.assertEqual(delete_ns_role_binding.call_count, 2)
        self.assertFalse(self.harness.charm._stored.started)

    @patch("utils.delete_namespaced_role_with_api")
    @patch("utils.delete_namespaced_role_binding_with_api")
    @patch("utils.delete_pod_security_policy_with_api")
    @patch("utils.get_k8s_version")
    def test_on_remove_gte_1_25(
        self, get_k8s_version, delete_psp, delete_ns_role_binding, delete_ns_role
    ):
        """Test remove hook >= 1.25.0."""
        get_k8s_version.return_value = (1, 25, 0)
        self.harness.charm.on.remove.emit()
        delete_psp.assert_not_called()
        self.assertEqual(delete_ns_role.call_count, 2)
        self.assertEqual(delete_ns_role_binding.call_count, 2)
        self.assertFalse(self.harness.charm._stored.started)

    @patch("utils.get_k8s_version")
    def test_get_pod_spec(self, get_k8s_version):
        """Test pod spec."""
        psp_rule = {
            "apiGroups": ["policy"],
            "resourceNames": ["speaker"],
            "resources": ["podsecuritypolicies"],
            "verbs": ["use"],
        }

        get_k8s_version.return_value = (1, 24, 6)
        spec = get_pod_spec("info", "secret")
        rules = spec["serviceAccount"]["roles"][0]["rules"]
        assert psp_rule in rules

        get_k8s_version.return_value = (1, 25, 0)
        spec = get_pod_spec("info", "secret")
        rules = spec["serviceAccount"]["roles"][0]["rules"]
        assert psp_rule not in rules


if __name__ == "__main__":
    unittest.main()
