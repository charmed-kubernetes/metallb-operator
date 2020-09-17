#!/usr/bin/env python3
"""Speaker component for the MetalLB bundle."""

import logging
import os
from base64 import b64encode

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


class MetallbSpeakerCharm(CharmBase):
    """MetalLB Speaker Charm."""

    _stored = StoredState()

    def __init__(self, *args):
        """Charm initialization for events observation."""
        super().__init__(*args)
        if not self.model.unit.is_leader():
            self.model.unit.status = WaitingStatus("Waiting for leadership")
            return
        self.framework.observe(self.on.start, self.on_start)
        self.framework.observe(self.on.remove, self.on_remove)
        # -- initialize states --
        self._stored.set_default(started=False)
        # -- base values --
        self._stored.set_default(namespace=os.environ["JUJU_MODEL_NAME"])
        self._stored.set_default(container_image='metallb/speaker:v0.9.3')

    def on_start(self, event):
        """Occurs upon start or installation of the charm."""
        logging.info('Setting the pod spec')
        self.model.unit.status = MaintenanceStatus("Configuring pod")
        self.set_pod_spec()

        response = utils.create_pod_security_policy_with_api(
            namespace=self._stored.namespace,
        )
        if not response:
            self.model.unit.status = \
                BlockedStatus("An error occured during init. Please check the logs.")
            return

        response = utils.create_namespaced_role_with_api(
            name='config-watcher',
            namespace=self._stored.namespace,
            labels={'app': 'metallb'},
            resources=['configmaps'],
            verbs=['get', 'list', 'watch']
        )
        if not response:
            print(response)
            self.model.unit.status = \
                BlockedStatus("An error occured during init. Please check the logs.")
            return

        response = utils.create_namespaced_role_with_api(
            name='pod-lister',
            namespace=self._stored.namespace,
            labels={'app': 'metallb'},
            resources=['pods'],
            verbs=['list']
        )
        if not response:
            self.model.unit.status = \
                BlockedStatus("An error occured during init. Please check the logs.")
            return

        response = utils.create_namespaced_role_binding_with_api(
            name='config-watcher',
            namespace=self._stored.namespace,
            labels={'app': 'metallb'},
            subject_name='speaker'
        )
        if not response:
            self.model.unit.status = \
                BlockedStatus("An error occured during init. Please check the logs.")
            return

        response = utils.create_namespaced_role_binding_with_api(
            name='pod-lister',
            namespace=self._stored.namespace,
            labels={'app': 'metallb'},
            subject_name='speaker'
        )
        if not response:
            self.model.unit.status = \
                BlockedStatus("An error occured during init. Please check the logs.")
            return

        self.model.unit.status = ActiveStatus("Ready")
        self._stored.started = True

    def on_remove(self, event):
        """Remove artifacts created by the K8s API."""
        self.model.unit.status = MaintenanceStatus("Removing pod")
        logger.info("Removing artifacts that were created with the k8s API")
        utils.delete_pod_security_policy_with_api(name='speaker')
        utils.delete_namespaced_role_binding_with_api(
            name='config-watcher',
            namespace=self._stored.namespace
        )
        utils.delete_namespaced_role_with_api(
            name='config-watcher',
            namespace=self._stored.namespace
        )
        utils.delete_namespaced_role_binding_with_api(
            name='pod-lister',
            namespace=self._stored.namespace
        )
        utils.delete_namespaced_role_with_api(
            name='pod-lister',
            namespace=self._stored.namespace
        )
        self.model.unit.status = ActiveStatus("Removing extra config done.")
        self._stored.started = False

    def set_pod_spec(self):
        """Set pod spec."""
        secret = utils._random_secret(128)
        self.model.pod.set_spec(
            {
                'version': 3,
                'serviceAccount': {
                    'roles': [{
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
                    }],
                },
                'containers': [{
                    'name': 'speaker',
                    'image': self._stored.container_image,
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
                            'secretkey':
                                b64encode(secret.encode('utf-8')).decode('utf-8')
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


if __name__ == "__main__":
    main(MetallbSpeakerCharm)
