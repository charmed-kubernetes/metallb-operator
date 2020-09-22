#!/usr/bin/env python3
"""Controller component for the MetalLB bundle."""

import logging
import os

from oci_image import OCIImageResource, OCIImageResourceError

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
    WaitingStatus,
)

import utils

logger = logging.getLogger(__name__)


class MetallbControllerCharm(CharmBase):
    """MetalLB Controller Charm."""

    _stored = StoredState()

    def __init__(self, *args):
        """Charm initialization for events observation."""
        super().__init__(*args)
        if not self.model.unit.is_leader():
            self.model.unit.status = WaitingStatus("Waiting for leadership")
            return
        self.image = OCIImageResource(self, 'metallb-controller-image')
        self.framework.observe(self.on.start, self.on_start)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.remove, self.on_remove)
        # -- initialize states --
        self._stored.set_default(started=False)
        self._stored.set_default(configured=False)
        # -- base values --
        self._stored.set_default(namespace=os.environ["JUJU_MODEL_NAME"])

    def _on_config_changed(self, event):
        if not self._stored.started:
            return
        self._stored.configured = False
        self.model.unit.status = MaintenanceStatus("Configuring pod")
        logger.info('Reapplying the updated pod spec')
        self.set_pod_spec()
        self.model.unit.status = ActiveStatus("Ready")
        self._stored.configured = True

    def on_start(self, event):
        """Occurs upon start or installation of the charm."""
        logging.info('Setting the pod spec')
        self.model.unit.status = MaintenanceStatus("Configuring pod")
        self.set_pod_spec()

        utils.create_pod_security_policy_with_api(namespace=self._stored.namespace)
        utils.create_namespaced_role_with_api(
            name='config-watcher',
            namespace=self._stored.namespace,
            labels={'app': 'metallb'},
            resources=['configmaps'],
            verbs=['get', 'list', 'watch']
        )
        utils.create_namespaced_role_binding_with_api(
            name='config-watcher',
            namespace=self._stored.namespace,
            labels={'app': 'metallb'},
            subject_name='metallb-controller'
        )

        self.model.unit.status = ActiveStatus("Ready")
        self._stored.started = True
        self._stored.configured = True

    def on_remove(self, event):
        """Remove of artifacts created by the K8s API."""
        self.model.unit.status = MaintenanceStatus("Removing pod")
        logger.info("Removing artifacts that were created with the k8s API")
        utils.delete_pod_security_policy_with_api(name='controller')
        utils.delete_namespaced_role_binding_with_api(
            name='config-watcher',
            namespace=self._stored.namespace
        )
        utils.delete_namespaced_role_with_api(
            name='config-watcher',
            namespace=self._stored.namespace
        )
        self.model.unit.status = ActiveStatus("Removing extra config done.")
        self._stored.configured = False
        self._stored.started = False

    def set_pod_spec(self):
        """Set pod spec."""
        iprange = self.model.config["iprange"].split(",")
        cm = "address-pools:\n- name: default\n  protocol: layer2\n  addresses:\n"
        for range in iprange:
            cm += "  - " + range + "\n"

        try:
            image_info = self.image.fetch()
        except OCIImageResourceError:
            logging.exception('An error occured while fetching the container image.')
            self.model.unit.status = BlockedStatus("Error fetching container image.")
            return

        self.model.pod.set_spec(
            {
                'version': 3,
                'serviceAccount': {
                    'roles': [{
                        'global': True,
                        'rules': [
                            {
                                'apiGroups': [''],
                                'resources': ['services'],
                                'verbs': ['get', 'list', 'watch', 'update'],
                            },
                            {
                                'apiGroups': [''],
                                'resources': ['services/status'],
                                'verbs': ['update'],
                            },
                            {
                                'apiGroups': [''],
                                'resources': ['events'],
                                'verbs': ['create', 'patch'],
                            },
                            {
                                'apiGroups': ['policy'],
                                'resourceNames': ['controller'],
                                'resources': ['podsecuritypolicies'],
                                'verbs': ['use'],
                            },
                        ],
                    }],
                },
                'containers': [{
                    'name': 'controller',
                    'imageDetails': image_info,
                    'imagePullPolicy': 'Always',
                    'ports': [{
                        'containerPort': 7472,
                        'protocol': 'TCP',
                        'name': 'monitoring'
                    }],
                    # TODO: add constraint fields once it exists in pod_spec
                    # bug : https://bugs.launchpad.net/juju/+bug/1893123
                    # 'resources': {
                    #     'limits': {
                    #         'cpu': '100m',
                    #         'memory': '100Mi',
                    #     }
                    # },
                    'kubernetes': {
                        'securityContext': {
                            'privileged': False,
                            'runAsNonRoot': True,
                            'runAsUser': 65534,
                            'readOnlyRootFilesystem': True,
                            'capabilities': {
                                'drop': ['ALL']
                            }
                        },
                        # fields do not exist in pod_spec
                        # 'TerminationGracePeriodSeconds': 0,
                    },
                }],
                'service': {
                    'annotations': {
                        'prometheus.io/port': '7472',
                        'prometheus.io/scrape': 'true'
                    }
                },
                'configMaps': {
                    'config': {
                        'config': cm
                    }
                }
            },
        )


if __name__ == "__main__":
    main(MetallbControllerCharm)
