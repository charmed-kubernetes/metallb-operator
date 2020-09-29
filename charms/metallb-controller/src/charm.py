#!/usr/bin/env python3
"""Controller component for the MetalLB bundle."""

import logging
import json
import os
from hashlib import md5

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


class MetalLBControllerCharm(CharmBase):
    """MetalLB Controller Charm."""

    _stored = StoredState()

    def __init__(self, *args):
        """Charm initialization for events observation."""
        super().__init__(*args)
        if not self.unit.is_leader():
            self.unit.status = WaitingStatus("Waiting for leadership")
            return
        self.image = OCIImageResource(self, 'metallb-controller-image')
        self.framework.observe(self.on.install, self._on_start)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.leader_elected, self._on_start)
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.remove, self._on_remove)
        # -- initialize states --
        self._stored.set_default(k8s_objects_created=False)
        self._stored.set_default(started=False)
        self._stored.set_default(config_hash=self._config_hash())
        # -- base values --
        self._stored.set_default(namespace=os.environ["JUJU_MODEL_NAME"])

    def _config_hash(self):
        data = json.dumps({
            'iprange': self.model.config['iprange'],
        }, sort_keys=True)
        return md5(data.encode('utf8')).hexdigest()

    def _on_start(self, event):
        """Occurs upon install, start, upgrade, and possibly config changed."""
        if self._stored.started:
            return
        self.unit.status = MaintenanceStatus("Fetching image information")
        try:
            image_info = self.image.fetch()
        except OCIImageResourceError:
            logging.exception('An error occured while fetching the image info')
            self.unit.status = BlockedStatus("Error fetching image information")
            return

        if not self._stored.k8s_objects_created:
            self.unit.status = MaintenanceStatus("Creating supplementary "
                                                 "Kubernetes objects")
            utils.create_k8s_objects(self._stored.namespace)
            self._stored.k8s_objects_created = True

        self.unit.status = MaintenanceStatus("Configuring pod")
        self.set_pod_spec(image_info)

        self.unit.status = ActiveStatus()
        self._stored.started = True

    def _on_upgrade(self, event):
        """Occurs when new charm code or image info is available."""
        self._stored.started = False
        self._on_start(event)

    def _on_config_changed(self, event):
        if self.model.config['protocol'] != 'layer2':
            self.unit.status = BlockedStatus('Invalid protocol; '
                                             'only "layer2" currently supported')
            return
        current_config_hash = self._config_hash()
        if current_config_hash != self._stored.config_hash:
            self._stored.started = False
            self._stored.config_hash = current_config_hash
            self._on_start(event)

    def _on_remove(self, event):
        """Remove of artifacts created by the K8s API."""
        self.unit.status = MaintenanceStatus("Removing supplementary "
                                             "Kubernetes objects")
        utils.remove_k8s_objects(self._stored.namespace)
        self.unit.status = MaintenanceStatus("Removing pod")
        self._stored.started = False
        self._stored.k8s_objects_created = False

    def set_pod_spec(self, image_info):
        """Set pod spec."""
        iprange = self.model.config["iprange"].split(",")
        cm = "address-pools:\n- name: default\n  protocol: layer2\n  addresses:\n"
        for range in iprange:
            cm += "  - " + range + "\n"

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
    main(MetalLBControllerCharm)
