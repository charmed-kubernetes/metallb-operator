
"Kubernetes utils library."

from kubernetes import client, config
from kubernetes.client.rest import ApiException
import logging
import os
import random
import string


logger = logging.getLogger(__name__)


def create_pod_security_policy_with_k8s_api(namespace):
    # Using the API because of LP:1886694
    logging.info('Creating pod security policy with K8s API')
    _load_kube_config()

    metadata = client.V1ObjectMeta(
        namespace = namespace,
        name = 'controller',
        labels = {'app':'metallb'}
    )
    policy_spec = client.PolicyV1beta1PodSecurityPolicySpec(
        allow_privilege_escalation = False,
        default_allow_privilege_escalation = False,
        fs_group = client.PolicyV1beta1FSGroupStrategyOptions(
            ranges = [client.PolicyV1beta1IDRange(max=65535, min=1)], 
            rule = 'MustRunAs'
        ),
        host_ipc = False,
        host_network = False,
        host_pid = False,
        privileged = False,
        read_only_root_filesystem = True,
        required_drop_capabilities = ['ALL'],
        run_as_user = client.PolicyV1beta1RunAsUserStrategyOptions(
            ranges = [client.PolicyV1beta1IDRange(max=65535, min=1)], 
            rule = 'MustRunAs'
        ),
        se_linux = client.PolicyV1beta1SELinuxStrategyOptions(
            rule = 'RunAsAny',
        ),
        supplemental_groups = client.PolicyV1beta1SupplementalGroupsStrategyOptions(
            ranges = [client.PolicyV1beta1IDRange(max=65535, min=1)], 
            rule = 'MustRunAs'
        ),
        volumes = ['configMap', 'secret', 'emptyDir'],
    )

    body = client.PolicyV1beta1PodSecurityPolicy(metadata=metadata, spec=policy_spec)

    with client.ApiClient() as api_client:
        api_instance = client.PolicyV1beta1Api(api_client)
        try:
            api_instance.create_pod_security_policy(body, pretty=True)
            return True
        except ApiException as err:
            logging.exception("Exception when calling PolicyV1beta1Api->create_pod_security_policy.")
            if err.status != 409:
                # ignoring 409 (AlreadyExists) errors
                return False
            else:
                return True


def create_namespaced_role_with_api(name, namespace, labels, resources, verbs, api_groups=['']):
    # Using API because of bug https://github.com/canonical/operator/issues/390
    logging.info('Creating namespaced role with K8s API')
    _load_kube_config()

    with client.ApiClient() as api_client:
        api_instance = client.RbacAuthorizationV1Api(api_client)
        body = client.V1Role(
            metadata = client.V1ObjectMeta(
                name = name,
                namespace = namespace,
                labels = labels
            ),
            rules = [client.V1PolicyRule(
                api_groups = api_groups,
                resources = resources,
                verbs = verbs,
            )]
        )
        try:
            api_instance.create_namespaced_role(namespace, body, pretty=True)
            return True
        except ApiException as err:
            logging.exception("Exception when calling RbacAuthorizationV1Api->create_namespaced_role.")
            if err.status != 409:
                # ignoring 409 (AlreadyExists) errors
                return False
            else:
                return True

def bind_role_with_api(name, namespace, labels, subject_name, subject_kind='ServiceAccount'):
    # Using API because of bug https://github.com/canonical/operator/issues/390
    logging.info('Creating role binding with K8s API')
    _load_kube_config()

    with client.ApiClient() as api_client:
        api_instance = client.RbacAuthorizationV1Api(api_client)
        body = client.V1RoleBinding(
            metadata = client.V1ObjectMeta(
                name = name,
                namespace = namespace,
                labels = labels
            ),
            role_ref = client.V1RoleRef(
                api_group = 'rbac.authorization.k8s.io',
                kind = 'Role',
                name = name,
            ),
            subjects = [
                client.V1Subject(
                    kind = subject_kind,
                    name = subject_name
                ),
            ]
        )
        try:
            api_instance.create_namespaced_role_binding(namespace, body, pretty=True)
            return True
        except ApiException as err:
            logging.exception("Exception when calling RbacAuthorizationV1Api->create_namespaced_role_binding.")
            if err.status != 409:
                # ignoring 409 (AlreadyExists) errors
                return False
            else:
                return True

def _random_secret(length):
    letters = string.ascii_letters
    result_str = ''.join(random.choice(letters) for i in range(length))
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
