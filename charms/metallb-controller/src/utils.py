"""Kubernetes utils library."""

import logging
import os
import random
import re
import string

from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)


def create_k8s_objects(namespace):
    """Create all supplementary K8s objects."""
    version_tup = get_k8s_version()
    if version_tup < (1, 25, 0):
        create_pod_security_policy_with_api(namespace=namespace)
    else:
        logging.info("Not creating PSP, kubelet version >= 1.25.0")

    create_namespaced_role_with_api(
        name="config-watcher",
        namespace=namespace,
        labels={"app": "metallb"},
        resources=["configmaps"],
        verbs=["get", "list", "watch"],
    )
    create_namespaced_role_binding_with_api(
        name="config-watcher",
        namespace=namespace,
        labels={"app": "metallb"},
        subject_name="metallb-controller",
    )


def remove_k8s_objects(namespace):
    """Remove all supplementary K8s objects."""
    version_tup = get_k8s_version()
    if version_tup < (1, 25, 0):
        delete_pod_security_policy_with_api(name="controller")
    else:
        logging.info("Skipping PSP removal, kubelet version >= 1.25.0")
    delete_namespaced_role_binding_with_api(name="config-watcher", namespace=namespace)
    delete_namespaced_role_with_api(name="config-watcher", namespace=namespace)


def create_pod_security_policy_with_api(namespace):
    """Create pod security policy."""
    # Using the API because of LP:1886694
    logging.info("Creating pod security policy with K8s API")
    _load_kube_config()

    metadata = client.V1ObjectMeta(
        namespace=namespace, name="controller", labels={"app": "metallb"}
    )
    policy_spec = client.PolicyV1beta1PodSecurityPolicySpec(
        allow_privilege_escalation=False,
        default_allow_privilege_escalation=False,
        fs_group=client.PolicyV1beta1FSGroupStrategyOptions(
            ranges=[client.PolicyV1beta1IDRange(max=65535, min=1)], rule="MustRunAs"
        ),
        host_ipc=False,
        host_network=False,
        host_pid=False,
        privileged=False,
        read_only_root_filesystem=True,
        required_drop_capabilities=["ALL"],
        run_as_user=client.PolicyV1beta1RunAsUserStrategyOptions(
            ranges=[client.PolicyV1beta1IDRange(max=65535, min=1)], rule="MustRunAs"
        ),
        se_linux=client.PolicyV1beta1SELinuxStrategyOptions(
            rule="RunAsAny",
        ),
        supplemental_groups=client.PolicyV1beta1SupplementalGroupsStrategyOptions(
            ranges=[client.PolicyV1beta1IDRange(max=65535, min=1)], rule="MustRunAs"
        ),
        volumes=["configMap", "secret", "emptyDir"],
    )

    body = client.PolicyV1beta1PodSecurityPolicy(metadata=metadata, spec=policy_spec)

    with client.ApiClient() as api_client:
        api_instance = client.PolicyV1beta1Api(api_client)
        try:
            api_instance.create_pod_security_policy(body, pretty=True)
        except ApiException as err:
            if err.status == 409:
                # ignore "already exists" errors so that we can recover from
                # partially failed setups
                return
            else:
                raise


def delete_pod_security_policy_with_api(name):
    """Delete pod security policy."""
    logging.info('Deleting pod security policy named "controller" with K8s API')
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
            if err.status == 409:
                # ignore "already exists" errors so that we can recover from
                # partially failed setups
                return
            else:
                raise


def delete_namespaced_role_with_api(name, namespace):
    """Delete namespaced role."""
    logging.info("Deleting namespaced role with K8s API")
    _load_kube_config()

    body = client.V1DeleteOptions()
    with client.ApiClient() as api_client:
        api_instance = client.RbacAuthorizationV1Api(api_client)
        try:
            api_instance.delete_namespaced_role(
                name=name, namespace=namespace, body=body, pretty=True
            )
        except ApiException:
            logging.exception(
                "Exception when calling RbacAuthorizationV1Api"
                "->delete_namespaced_role."
            )


def create_namespaced_role_binding_with_api(
    name, namespace, labels, subject_name, subject_kind="ServiceAccount"
):
    """Bind namespaced role to subject."""
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
            if err.status == 409:
                # ignore "already exists" errors so that we can recover from
                # partially failed setups
                return
            else:
                raise


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
                "Exception when calling RbacAuthorizationV1Api"
                "->delete_namespaced_role_binding."
            )


def get_k8s_version():
    """Get k8s version with K8s API."""
    logging.info("Getting k8s version with API")
    _load_kube_config()

    v1 = client.CoreV1Api()
    try:
        api_response = v1.list_node(pretty=True)
        node = api_response.items[0]
        kubelet_version = node.status.node_info.kubelet_version
        version_tup = tuple(int(q) for q in re.findall("[0-9]+", kubelet_version)[:3])
        return version_tup
    except ApiException as e:
        print("Exception when calling CoreV1Api->list_node: %s\n" % e)


def get_pod_spec(image_info, cm):
    """Get pod spec."""
    version_tup = get_k8s_version()
    rules = [
        {
            "apiGroups": [""],
            "resources": ["services"],
            "verbs": ["get", "list", "watch", "update"],
        },
        {
            "apiGroups": [""],
            "resources": ["services/status"],
            "verbs": ["update"],
        },
        {
            "apiGroups": [""],
            "resources": ["events"],
            "verbs": ["create", "patch"],
        },
    ]
    if version_tup < (1, 25, 0):
        logging.info("Appending PSP-related podspec rules, kubelet version < 1.25.0")
        rules.append(
            {
                "apiGroups": ["policy"],
                "resourceNames": ["controller"],
                "resources": ["podsecuritypolicies"],
                "verbs": ["use"],
            }
        )
    else:
        logging.info("Skipping PSP-related podspec rules, kubelet version >= 1.25.0")

    spec = {
        "version": 3,
        "serviceAccount": {
            "roles": [
                {
                    "global": True,
                    "rules": rules,
                }
            ],
        },
        "containers": [
            {
                "name": "controller",
                "imageDetails": image_info,
                "imagePullPolicy": "Always",
                "ports": [
                    {
                        "containerPort": 7472,
                        "protocol": "TCP",
                        "name": "monitoring",
                    }
                ],
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
                        "privileged": False,
                        "runAsNonRoot": True,
                        "runAsUser": 65534,
                        "readOnlyRootFilesystem": True,
                        "capabilities": {"drop": ["ALL"]},
                    },
                    # fields do not exist in pod_spec
                    # 'TerminationGracePeriodSeconds': 0,
                },
            }
        ],
        "service": {
            "annotations": {
                "prometheus.io/port": "7472",
                "prometheus.io/scrape": "true",
            }
        },
        "configMaps": {"config": {"config": cm}},
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
