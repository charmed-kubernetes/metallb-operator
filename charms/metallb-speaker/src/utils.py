"""Kubernetes utils library."""

import logging
import os
import random
import string
import sys

from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)


def create_k8s_objects(namespace):
    """Create all supplementary K8s objects."""
    if supports_policy_v1_beta():
        create_pod_security_policy_with_api(namespace=namespace)
    else:
        logging.info("Not creating PSP, doesn't support policy_v1_beta")
    create_namespaced_role_with_api(
        name="config-watcher",
        namespace=namespace,
        labels={"app": "metallb"},
        resources=["configmaps"],
        verbs=["get", "list", "watch"],
    )
    create_namespaced_role_with_api(
        name="pod-lister",
        namespace=namespace,
        labels={"app": "metallb"},
        resources=["pods"],
        verbs=["list"],
    )
    create_namespaced_role_binding_with_api(
        name="config-watcher",
        namespace=namespace,
        labels={"app": "metallb"},
        subject_name="metallb-speaker",
    )
    create_namespaced_role_binding_with_api(
        name="pod-lister",
        namespace=namespace,
        labels={"app": "metallb"},
        subject_name="metallb-speaker",
    )


def remove_k8s_objects(namespace):
    """Remove all supplementary K8s objects."""
    if supports_policy_v1_beta():
        delete_pod_security_policy_with_api(name="speaker")
    else:
        logging.info("Skipping PSP removal, doesn't support policy_v1_beta")

    delete_namespaced_role_binding_with_api(name="config-watcher", namespace=namespace)
    delete_namespaced_role_with_api(name="config-watcher", namespace=namespace)
    delete_namespaced_role_binding_with_api(name="pod-lister", namespace=namespace)
    delete_namespaced_role_with_api(name="pod-lister", namespace=namespace)


def create_pod_security_policy_with_api(namespace):
    """Create pod security policy."""
    # Using the API because of LP:1886694
    logging.info("Creating pod security policy with K8s API")
    _load_kube_config()

    metadata = client.V1ObjectMeta(
        namespace=namespace, name="speaker", labels={"app": "metallb"}
    )
    policy_spec = client.PolicyV1beta1PodSecurityPolicySpec(
        allow_privilege_escalation=False,
        allowed_capabilities=[
            "NET_ADMIN",
            "NET_RAW",
            "SYS_ADMIN",
        ],
        default_allow_privilege_escalation=False,
        fs_group=client.PolicyV1beta1FSGroupStrategyOptions(rule="RunAsAny"),
        host_ipc=False,
        host_network=True,
        host_pid=False,
        host_ports=[
            client.PolicyV1beta1HostPortRange(
                max=7472,
                min=7472,
            )
        ],
        privileged=True,
        read_only_root_filesystem=True,
        required_drop_capabilities=["ALL"],
        run_as_user=client.PolicyV1beta1RunAsUserStrategyOptions(rule="RunAsAny"),
        se_linux=client.PolicyV1beta1SELinuxStrategyOptions(
            rule="RunAsAny",
        ),
        supplemental_groups=client.PolicyV1beta1SupplementalGroupsStrategyOptions(
            rule="RunAsAny"
        ),
        volumes=["configMap", "secret", "emptyDir"],
    )

    body = client.PolicyV1beta1PodSecurityPolicy(metadata=metadata, spec=policy_spec)

    with client.ApiClient() as api_client:
        api_instance = client.PolicyV1beta1Api(api_client)
        try:
            api_instance.create_pod_security_policy(body, pretty=True)
        except ApiException as err:
            logging.exception(
                "Exception when calling PolicyV1beta1Api"
                "->create_pod_security_policy."
            )
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
            logging.exception(
                "Exception when calling PolicyV1beta1Api"
                "->delete_pod_security_policy."
            )


def create_namespaced_role_with_api(
    name, namespace, labels, resources, verbs, api_groups=[""]
):
    """Create namespaced role."""
    # Using API because of bug https://bugs.launchpad.net/juju/+bug/1896076
    logging.info("Creating namespaced role with K8s API")
    _load_kube_config()

    body = client.V1Role(
        metadata=client.V1ObjectMeta(name=name, namespace=namespace, labels=labels),
        rules=[
            client.V1PolicyRule(
                api_groups=api_groups,
                resources=resources,
                verbs=verbs,
            )
        ],
    )
    with client.ApiClient() as api_client:
        api_instance = client.RbacAuthorizationV1Api(api_client)
        try:
            api_instance.create_namespaced_role(namespace, body, pretty=True)
        except ApiException as err:
            logging.exception(
                "Exception when calling RbacAuthorizationV1Api"
                "->create_namespaced_role."
            )
            if err.status != 409:
                # Hook error except for 409 (AlreadyExists) errors
                sys.exit(1)


def delete_namespaced_role_with_api(name, namespace):
    """Delete a namespaced role."""
    logging.info("Deleting namespaced role with K8s API")
    _load_kube_config()

    body = client.V1DeleteOptions()
    with client.ApiClient() as api_client:
        api_instance = client.RbacAuthorizationV1Api(api_client)
        try:
            api_instance.delete_namespaced_role(
                name=name, namespace=namespace, body=body, pretty=True
            )
        except ApiException as err:
            logging.exception(
                "Exception when calling RbacAuthorizationV1Api"
                "->delete_namespaced_role."
            )
            if err.status != 409:
                # Hook error except for 409 (AlreadyExists) errors
                sys.exit(1)


def create_namespaced_role_binding_with_api(
    name, namespace, labels, subject_name, subject_kind="ServiceAccount"
):
    """Bind a namespaced role to a subject."""
    # Using API because of bug https://bugs.launchpad.net/juju/+bug/1896076
    logging.info("Creating role binding with K8s API")
    _load_kube_config()

    body = client.V1RoleBinding(
        metadata=client.V1ObjectMeta(name=name, namespace=namespace, labels=labels),
        role_ref=client.V1RoleRef(
            api_group="rbac.authorization.k8s.io",
            kind="Role",
            name=name,
        ),
        subjects=[
            client.V1Subject(kind=subject_kind, name=subject_name),
        ],
    )
    with client.ApiClient() as api_client:
        api_instance = client.RbacAuthorizationV1Api(api_client)
        try:
            api_instance.create_namespaced_role_binding(namespace, body, pretty=True)
        except ApiException as err:
            logging.exception(
                "Exception when calling RbacAuthorizationV1Api"
                "->create_namespaced_role_binding."
            )
            if err.status != 409:
                # Hook error except for 409 (AlreadyExists) errors
                sys.exit(1)


def delete_namespaced_role_binding_with_api(name, namespace):
    """Delete namespaced role binding with K8s API."""
    logging.info("Deleting namespaced role binding with API")
    _load_kube_config()

    body = client.V1DeleteOptions()
    with client.ApiClient() as api_client:
        api_instance = client.RbacAuthorizationV1Api(api_client)
        try:
            api_instance.delete_namespaced_role_binding(
                name=name, namespace=namespace, body=body, pretty=True
            )
        except ApiException:
            logging.exception(
                "Exception when calling RbacAuthorizationV1Api->"
                "delete_namespaced_role_binding."
            )


def supports_policy_v1_beta():
    """Determine if k8s api supports PolicyV1/beta."""
    logging.info("Determine if k8s api supports PolicyV1/beta")
    _load_kube_config()

    with client.ApiClient() as api_client:
        api_instance = client.PolicyV1beta1Api(api_client)
        try:
            api_instance.get_api_resources()
        except ApiException as err:
            if err.status == 404:
                return False
    return True


def get_pod_spec(image_info, secret_key):
    """Get pod spec."""
    policyv1_beta = supports_policy_v1_beta()
    rules = [
        {
            "apiGroups": [""],
            "resources": ["services", "endpoints", "nodes"],
            "verbs": ["get", "list", "watch"],
        },
        {
            "apiGroups": [""],
            "resources": ["events"],
            "verbs": ["create", "patch"],
        },
    ]
    if policyv1_beta:
        logging.info("Appending PSP-related podspec rules, policyv1_beta supported")
        rules.append(
            {
                "apiGroups": ["policy"],
                "resourceNames": ["speaker"],
                "resources": ["podsecuritypolicies"],
                "verbs": ["use"],
            }
        )
    else:
        logging.info("Skipping PSP-related podspec rules, policyv1_beta not supported")

    spec = {
        "version": 3,
        "serviceAccount": {
            "roles": [{"global": True, "rules": rules}],
        },
        "containers": [
            {
                "name": "speaker",
                "imageDetails": image_info,
                "imagePullPolicy": "Always",
                "ports": [
                    {
                        "containerPort": 7472,
                        "protocol": "TCP",
                        "name": "monitoring",
                    }
                ],
                "envConfig": {
                    "METALLB_NODE_NAME": {
                        "field": {"path": "spec.nodeName", "api-version": "v1"}
                    },
                    "METALLB_HOST": {
                        "field": {"path": "status.hostIP", "api-version": "v1"}
                    },
                    "METALLB_ML_BIND_ADDR": {
                        "field": {"path": "status.podIP", "api-version": "v1"}
                    },
                    "METALLB_ML_LABELS": "app=metallb,component=speaker",
                    "METALLB_ML_NAMESPACE": {
                        "field": {
                            "path": "metadata.namespace",
                            "api-version": "v1",
                        }
                    },
                    "METALLB_ML_SECRET_KEY": {
                        "secret": {"name": "memberlist", "key": "secretkey"}
                    },
                },
                # TODO: add constraint fields once it exists in pod_spec
                # bug : https://bugs.launchpad.net/juju/+bug/1893123
                # 'resources': {
                #     'limits': {
                #         'cpu': '100m',
                #         'memory': '100Mi',
                #     }
                # },
                "kubernetes": {
                    "securityContext": {
                        "allowPrivilegeEscalation": False,
                        "readOnlyRootFilesystem": True,
                        "capabilities": {
                            "add": ["NET_ADMIN", "NET_RAW", "SYS_ADMIN"],
                            "drop": ["ALL"],
                        },
                    },
                    # fields do not exist in pod_spec
                    # 'TerminationGracePeriodSeconds': 2,
                },
            }
        ],
        "kubernetesResources": {
            "pod": {"hostNetwork": True},
            "secrets": [
                {
                    "name": "memberlist",
                    "type": "Opaque",
                    "data": {
                        "secretkey": secret_key,
                    },
                }
            ],
        },
        "service": {
            "annotations": {
                "prometheus.io/port": "7472",
                "prometheus.io/scrape": "true",
            }
        },
    }
    return spec


def _random_secret(length):
    letters = string.ascii_letters
    result_str = "".join(random.SystemRandom().choice(letters) for i in range(length))
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
