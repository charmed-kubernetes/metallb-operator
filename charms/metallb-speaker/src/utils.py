"""Kubernetes utils library."""

import logging
import os
import random
import string
import sys

from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)


def create_pod_security_policy_with_api(namespace):
    """Create pod security policy."""
    # Using the API because of LP:1886694
    logging.info('Creating pod security policy with K8s API')
    _load_kube_config()

    metadata = client.V1ObjectMeta(
        namespace=namespace,
        name='speaker',
        labels={'app': 'metallb'}
    )
    policy_spec = client.PolicyV1beta1PodSecurityPolicySpec(
        allow_privilege_escalation=False,
        allowed_capabilities=[
            'NET_ADMIN',
            'NET_RAW',
            'SYS_ADMIN',
        ],
        default_allow_privilege_escalation=False,
        fs_group=client.PolicyV1beta1FSGroupStrategyOptions(
            rule='RunAsAny'
        ),
        host_ipc=False,
        host_network=True,
        host_pid=False,
        host_ports=[client.PolicyV1beta1HostPortRange(
            max=7472,
            min=7472,
        )],
        privileged=True,
        read_only_root_filesystem=True,
        required_drop_capabilities=['ALL'],
        run_as_user=client.PolicyV1beta1RunAsUserStrategyOptions(
            rule='RunAsAny'
        ),
        se_linux=client.PolicyV1beta1SELinuxStrategyOptions(
            rule='RunAsAny',
        ),
        supplemental_groups=client.PolicyV1beta1SupplementalGroupsStrategyOptions(
            rule='RunAsAny'
        ),
        volumes=['configMap', 'secret', 'emptyDir'],
    )

    body = client.PolicyV1beta1PodSecurityPolicy(metadata=metadata, spec=policy_spec)

    with client.ApiClient() as api_client:
        api_instance = client.PolicyV1beta1Api(api_client)
        try:
            api_instance.create_pod_security_policy(body, pretty=True)
        except ApiException as err:
            logging.exception("Exception when calling PolicyV1beta1Api"
                              "->create_pod_security_policy.")
            if err.status != 409:
                # Hook error except for 409 (AlreadyExists) errors
                sys.exit(1)


def delete_pod_security_policy_with_api(name):
    """Delete pod security policy."""
    logging.info('Deleting pod security policy named "speaker" with K8s API')
    _load_kube_config()

    body = client.V1DeleteOptions()
    with client.ApiClient() as api_client:
        api_instance = client.PolicyV1beta1Api(api_client)
        try:
            api_instance.delete_pod_security_policy(name=name, body=body, pretty=True)
        except ApiException:
            logging.exception("Exception when calling PolicyV1beta1Api"
                              "->delete_pod_security_policy.")


def create_namespaced_role_with_api(name, namespace, labels, resources,
                                    verbs, api_groups=['']):
    """Create namespaced role."""
    # Using API because of bug https://bugs.launchpad.net/juju/+bug/1896076
    logging.info('Creating namespaced role with K8s API')
    _load_kube_config()

    body = client.V1Role(
        metadata=client.V1ObjectMeta(
            name=name,
            namespace=namespace,
            labels=labels
        ),
        rules=[client.V1PolicyRule(
            api_groups=api_groups,
            resources=resources,
            verbs=verbs,
        )]
    )
    with client.ApiClient() as api_client:
        api_instance = client.RbacAuthorizationV1Api(api_client)
        try:
            api_instance.create_namespaced_role(namespace, body, pretty=True)
        except ApiException as err:
            logging.exception("Exception when calling RbacAuthorizationV1Api"
                              "->create_namespaced_role.")
            if err.status != 409:
                # Hook error except for 409 (AlreadyExists) errors
                sys.exit(1)


def delete_namespaced_role_with_api(name, namespace):
    """Delete a namespaced role."""
    logging.info('Deleting namespaced role with K8s API')
    _load_kube_config()

    body = client.V1DeleteOptions()
    with client.ApiClient() as api_client:
        api_instance = client.RbacAuthorizationV1Api(api_client)
        try:
            api_instance.delete_namespaced_role(
                name=name,
                namespace=namespace,
                body=body,
                pretty=True
            )
        except ApiException:
            logging.exception("Exception when calling RbacAuthorizationV1Api"
                              "->delete_namespaced_role.")


def create_namespaced_role_binding_with_api(name, namespace, labels, subject_name,
                                            subject_kind='ServiceAccount'):
    """Bind a namespaced role to a subject."""
    # Using API because of bug https://bugs.launchpad.net/juju/+bug/1896076
    logging.info('Creating role binding with K8s API')
    _load_kube_config()

    body = client.V1RoleBinding(
        metadata=client.V1ObjectMeta(
            name=name,
            namespace=namespace,
            labels=labels
        ),
        role_ref=client.V1RoleRef(
            api_group='rbac.authorization.k8s.io',
            kind='Role',
            name=name,
        ),
        subjects=[
            client.V1Subject(
                kind=subject_kind,
                name=subject_name
            ),
        ]
    )
    with client.ApiClient() as api_client:
        api_instance = client.RbacAuthorizationV1Api(api_client)
        try:
            api_instance.create_namespaced_role_binding(namespace, body, pretty=True)
        except ApiException as err:
            logging.exception("Exception when calling RbacAuthorizationV1Api"
                              "->create_namespaced_role_binding.")
            if err.status != 409:
                # Hook error except for 409 (AlreadyExists) errors
                sys.exit(1)


def delete_namespaced_role_binding_with_api(name, namespace):
    """Delete namespaced role binding with K8s API."""
    logging.info('Deleting namespaced role binding with API')
    _load_kube_config()

    body = client.V1DeleteOptions()
    with client.ApiClient() as api_client:
        api_instance = client.RbacAuthorizationV1Api(api_client)
        try:
            api_instance.delete_namespaced_role_binding(
                name=name,
                namespace=namespace,
                body=body,
                pretty=True
            )
        except ApiException:
            logging.exception("Exception when calling RbacAuthorizationV1Api->"
                              "delete_namespaced_role_binding.")


def _random_secret(length):
    letters = string.ascii_letters
    result_str = ''.join(random.SystemRandom().choice(letters) for i in range(length))
    return result_str


def _load_kube_config():
    # TODO: Remove this workaround when bug LP:1892255 is fixed
    from pathlib import Path
    os.environ.update(
        dict(
            e.split("=")
            for e in Path("/proc/1/environ").read_text().split("\x00")
            if "KUBERNETES_SERVICE" in e
        )
    )
    # end workaround
    config.load_incluster_config()
