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
    @patch("utils.supports_policy_v1_beta")
    def test_on_start_lt_1_25(
        self,
        supports_policy_v1_beta,
        create_psp,
        create_ns_role,
        create_ns_role_binding,
    ):
        """Test installation < 1.25.0."""
        supports_policy_v1_beta.return_value = True
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
    @patch("utils.supports_policy_v1_beta")
    def test_on_start_gte_1_25(
        self,
        supports_policy_v1_beta,
        create_psp,
        create_ns_role,
        create_ns_role_binding,
    ):
        """Test installation >= 1.2.50."""
        supports_policy_v1_beta.return_value = False
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
    @patch("utils.supports_policy_v1_beta")
    def test_on_remove_lt_1_25(
        self,
        supports_policy_v1_beta,
        delete_psp,
        delete_ns_role_binding,
        delete_ns_role,
    ):
        """Test remove hook < 1.25.0."""
        supports_policy_v1_beta.return_value = True
        self.harness.charm.on.remove.emit()
        delete_psp.assert_called_once()
        self.assertEqual(delete_ns_role.call_count, 2)
        self.assertEqual(delete_ns_role_binding.call_count, 2)
        self.assertFalse(self.harness.charm._stored.started)

    @patch("utils.delete_namespaced_role_with_api")
    @patch("utils.delete_namespaced_role_binding_with_api")
    @patch("utils.delete_pod_security_policy_with_api")
    @patch("utils.supports_policy_v1_beta")
    def test_on_remove_gte_1_25(
        self,
        supports_policy_v1_beta,
        delete_psp,
        delete_ns_role_binding,
        delete_ns_role,
    ):
        """Test remove hook >= 1.25.0."""
        supports_policy_v1_beta.return_value = False
        self.harness.charm.on.remove.emit()
        delete_psp.assert_not_called()
        self.assertEqual(delete_ns_role.call_count, 2)
        self.assertEqual(delete_ns_role_binding.call_count, 2)
        self.assertFalse(self.harness.charm._stored.started)

    @patch("utils.supports_policy_v1_beta")
    def test_get_pod_spec(self, supports_policy_v1_beta):
        """Test pod spec."""
        psp_rule = {
            "apiGroups": ["policy"],
            "resourceNames": ["speaker"],
            "resources": ["podsecuritypolicies"],
            "verbs": ["use"],
        }

        supports_policy_v1_beta.return_value = True
        spec = get_pod_spec("info", "secret")
        rules = spec["serviceAccount"]["roles"][0]["rules"]
        assert psp_rule in rules

        supports_policy_v1_beta.return_value = False
        spec = get_pod_spec("info", "secret")
        rules = spec["serviceAccount"]["roles"][0]["rules"]
        assert psp_rule not in rules


if __name__ == "__main__":
    unittest.main()
