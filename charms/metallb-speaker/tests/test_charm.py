"""Unit tests."""

import unittest
from unittest.mock import Mock, patch

from charm import MetallbSpeakerCharm

from ops.testing import Harness


class TestCharm(unittest.TestCase):
    """MetalLB Controller Charm Unit Tests."""

    @patch.dict('charm.os.environ', {'JUJU_MODEL_NAME': 'unit-test-metallb'})
    def setUp(self):
        """Test setup."""
        self.harness = Harness(MetallbSpeakerCharm)
        self.harness.set_leader(is_leader=True)
        self.harness.begin()

    @patch.dict('charm.os.environ', {'JUJU_MODEL_NAME': 'unit-test-metallb'})
    @patch("utils.create_namespaced_role_binding_with_api")
    @patch("utils.create_namespaced_role_with_api")
    @patch("utils.create_pod_security_policy_with_api")
    def test_on_start(self, create_psp, create_ns_role, create_ns_role_binding):
        """Test installation."""
        mock_pod_spec = self.harness.charm.set_pod_spec = Mock()
        self.assertFalse(self.harness.charm._stored.started)
        self.harness.charm.on.start.emit()
        mock_pod_spec.assert_called_once()
        create_psp.assert_called_once()
        self.assertEqual(create_ns_role.call_count, 2)
        self.assertEqual(create_ns_role_binding.call_count, 2)
        self.assertTrue(self.harness.charm._stored.started)

    @patch("utils.delete_namespaced_role_with_api")
    @patch("utils.delete_namespaced_role_binding_with_api")
    @patch("utils.delete_pod_security_policy_with_api")
    def test_on_remove(self, delete_psp, delete_ns_role_binding, delete_ns_role):
        """Test remove hook."""
        self.harness.charm.on.remove.emit()
        delete_psp.assert_called_once()
        self.assertEqual(delete_ns_role.call_count, 2)
        self.assertEqual(delete_ns_role_binding.call_count, 2)
        self.assertFalse(self.harness.charm._stored.started)


if __name__ == "__main__":
    unittest.main()
