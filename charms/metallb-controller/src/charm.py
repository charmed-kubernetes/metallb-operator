#!/usr/bin/env python3
# Copyright 2020 Camille Rodriguez
# See LICENSE file for licensing details.

from kubernetes import client, config
from kubernetes.client.rest import ApiException
import os
import logging

from ops.charm import CharmBase
from ops.main import main
from ops.framework import StoredState
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
)

import utils

logger = logging.getLogger(__name__)


class MetallbControllerCharm(CharmBase):
    _stored = StoredState()

    NAMESPACE = os.environ["JUJU_MODEL_NAME"]

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.start, self.on_start)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self._stored.set_default(things=[])

    def _on_config_changed(self, _):
        current = self.model.config["protocol"]
        if current not in self._stored.things:
            logger.debug("found a new thing: %r", current)
            self._stored.things.append(current)

    def on_start(self, event):
        if not self.framework.model.unit.is_leader():
            return

        logging.info('Setting the pod spec')
        self.framework.model.unit.status = MaintenanceStatus("Configuring pod")
        iprange = self.model.config["iprange"]

        self.framework.model.pod.set_spec(
            {
                'version': 3,
                'serviceAccount': {
                    'roles' :  [{
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
                    },
                  ],
                },
                'containers': [{
                    'name': 'controller',
                    'image': 'metallb/controller:v0.9.3',
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
                        'config' : 'address-pools:\n- name: default\n  protocol: layer2\n  addresses:\n  - ' + iprange
                    }
                }
            },
        )

        response = utils.create_pod_security_policy_with_k8s_api(
            namespace=self.NAMESPACE,
        )
        if not response:
            self.framework.model.unit.status = BlockedStatus("An error occured during init. Please check the logs.")
            return

        response = utils.create_namespaced_role_with_api(
            name='config-watcher',
            namespace = self.NAMESPACE,
            labels={'app': 'metallb'},
            resources=['configmaps'],
            verbs=['get','list','watch']
        )
        if not response:
            self.framework.model.unit.status = BlockedStatus("An error occured during init. Please check the logs.")
            return
       
        response = utils.bind_role_with_api(
            name='config-watcher',
            namespace = self.NAMESPACE,
            labels={'app': 'metallb'}, 
            subject_name='controller'
        )
        if not response:
            self.framework.model.unit.status = BlockedStatus("An error occured during init. Please check the logs.")
            return

        self.framework.model.unit.status = ActiveStatus("Ready")


if __name__ == "__main__":
    main(MetallbControllerCharm)
