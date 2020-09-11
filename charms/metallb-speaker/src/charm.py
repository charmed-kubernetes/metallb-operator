#!/usr/bin/env python3
# Copyright 2020 Camille Rodriguez
# See LICENSE file for licensing details.

from base64 import b64encode
import logging
import os

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


class MetallbSpeakerCharm(CharmBase):
    _stored = StoredState()

    NAMESPACE = os.environ["JUJU_MODEL_NAME"]
    CONTAINER_IMAGE = 'metallb/speaker:v0.9.3'

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.start, self.on_start)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.remove, self.on_remove)
        self._stored.set_default(things=[])

    def _on_config_changed(self, _):
        current = self.model.config["thing"]
        if current not in self._stored.things:
            logger.debug("found a new thing: %r", current)
            self._stored.things.append(current)

    def on_start(self, event):
        if not self.framework.model.unit.is_leader():
            return

        logging.info('Setting the pod spec')
        self.framework.model.unit.status = MaintenanceStatus("Configuring pod")
        secret = utils._random_secret(128)

        self.framework.model.pod.set_spec(
            {
                'version': 3,
                'serviceAccount': {
                    'roles' :  [{
                        'global': True,
                        'rules': [
                            {
                                'apiGroups': [''],
                                'resources': ['services', 'endpoints', 'nodes'],
                                'verbs': ['get', 'list', 'watch'],
                            },
                            {
                                'apiGroups': [''],
                                'resources': ['events'],
                                'verbs': ['create', 'patch'],
                            },
                            {
                                'apiGroups': ['policy'],
                                'resourceNames': ['speaker'],
                                'resources': ['podsecuritypolicies'],
                                'verbs': ['use'],
                            },
                        ],
                    },
                  ],
                },
                'containers': [{
                    'name': 'speaker',
                    'image': self.CONTAINER_IMAGE,
                    'imagePullPolicy': 'Always',
                    'ports': [{
                        'containerPort': 7472,
                        'protocol': 'TCP',
                        'name': 'monitoring'
                    }],
                    'envConfig': {
                        'METALLB_NODE_NAME': {
                            'field': {
                                'path': 'spec.nodeName',
                                'api-version': 'v1'
                            }
                        },
                        'METALLB_HOST': {
                            'field': {
                                'path': 'status.hostIP',
                                'api-version': 'v1'
                            }
                        },
                        'METALLB_ML_BIND_ADDR': {
                            'field': {
                                'path': 'status.podIP',
                                'api-version': 'v1'
                            }
                        },
                        'METALLB_ML_LABELS': "app=metallb,component=speaker",
                        'METALLB_ML_NAMESPACE': {
                            'field': {
                                'path': 'metadata.namespace',
                                'api-version': 'v1'
                            }
                        },
                        'METALLB_ML_SECRET_KEY': {
                            'secret': {
                                'name': 'memberlist',
                                'key': 'secretkey'
                            }
                        }
                    },
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
                            'allowPrivilegeEscalation': False,
                            'readOnlyRootFilesystem': True,
                            'capabilities': {
                                'add': ['NET_ADMIN', 'NET_RAW', 'SYS_ADMIN'],
                                'drop': ['ALL']
                            },
                        },
                        # fields do not exist in pod_spec
                        # 'TerminationGracePeriodSeconds': 2, 
                    },
                }],
                'kubernetesResources': {
                    'secrets': [{
                        'name': 'memberlist',
                        'type': 'Opaque',
                        'data': {
                            'secretkey': b64encode(secret.encode('utf-8')).decode('utf-8')
                        }
                    }]
                },
                'service': {
                    'annotations': {
                        'prometheus.io/port': '7472',
                        'prometheus.io/scrape': 'true'
                    }
                },
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

        response = utils.create_namespaced_role_with_api(
            name='pod-lister',
            namespace = self.NAMESPACE,
            labels={'app': 'metallb'},
            resources=['pods'],
            verbs=['list']
        )
        if not response:
            self.framework.model.unit.status = BlockedStatus("An error occured during init. Please check the logs.")
            return

        response = utils.bind_role_with_api(
            name='config-watcher',
            namespace = self.NAMESPACE,
            labels={'app': 'metallb'}, 
            subject_name='speaker'
        )
        if not response:
            self.framework.model.unit.status = BlockedStatus("An error occured during init. Please check the logs.")
            return

        response = utils.bind_role_with_api(
            name='pod-lister',
            namespace = self.NAMESPACE,
            labels={'app': 'metallb'}, 
            subject_name='speaker'
        )
        if not response:
            self.framework.model.unit.status = BlockedStatus("An error occured during init. Please check the logs.")
            return

        self.framework.model.unit.status = ActiveStatus("Ready")

    def on_remove(self, event):
        if not self.framework.model.unit.is_leader():
            return


if __name__ == "__main__":
    main(MetallbSpeakerCharm)
