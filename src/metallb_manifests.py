import logging
from typing import Dict

from lightkube.codecs import AnyResource
from ops.manifests import ConfigRegistry, ManifestLabel, Manifests, Patch

logger = logging.getLogger(__name__)


class PatchNamespace(Patch):
    def __call__(self, obj: AnyResource):
        ns_name = self.manifests.config["namespace"]
        # Patch the namespace object itself
        if obj.kind == "Namespace":
            logger.info(f"Patching namespace name for {obj.kind} {obj.metadata.name} to {ns_name}")
            obj.metadata.name = ns_name
            return

        # Patch the addresspools CRD
        if obj.metadata.name == "addresspools.metallb.io":
            logger.info(f"Patching namespace for {obj.kind} {obj.metadata.name} to {ns_name}")
            obj.spec.conversion.webhook.clientConfig.service.namespace = ns_name
            return

        # Patch the bgppeers CRD
        if obj.metadata.name == "bgppeers.metallb.io":
            logger.info(f"Patching namespace for {obj.kind} {obj.metadata.name} to {ns_name}")
            obj.spec.conversion.webhook.clientConfig.service.namespace = ns_name
            return

        # patch ns in webhook configs
        if (
            obj.kind == "ValidatingWebhookConfiguration"
            or obj.kind == "MutatingWebhookConfiguration"
        ):
            for webhook in obj.webhooks:
                logger.info(
                    f"Patching clientConfig service namespace for {obj.kind} {obj.metadata.name} to {ns_name}"
                )
                webhook.clientConfig.service.namespace = ns_name

        # patch ns in RoleBinding (both ns and subjects ns)
        if obj.kind == "RoleBinding":
            logger.info(f"Patching namespace for {obj.kind} {obj.metadata.name} to {ns_name}")
            obj.metadata.namespace = ns_name
            for subject in obj.subjects:
                logger.info(
                    f"Patching subject namespace for {subject.kind} {subject.name} to {ns_name}"
                )
                subject.namespace = ns_name
            return

        # patch ns in ClusterRoleBinding subjects
        if obj.kind == "ClusterRoleBinding":
            for subject in obj.subjects:
                logger.info(
                    f"Patching subject namespace for {subject.kind} {subject.name} to {ns_name}"
                )
                subject.namespace = ns_name
            return

        # Patch any resources with a namespace in their metadata
        if obj.metadata.namespace:
            logger.info(f"Patching namespace for {obj.kind} {obj.metadata.name} to {ns_name}")
            obj.metadata.namespace = ns_name
            return


class PatchNodeSelector(Patch):
    def __call__(self, obj: AnyResource):
        node_selector: str = self.manifests.config.get("node-selector")
        parsed = dict(
            selector.split("=", 1)
            for selector in node_selector.split()
            if selector and "=" in selector
        )
        if obj.kind == "DaemonSet" or obj.kind == "Deployment":
            logger.info(f"Patching nodeSelector for {obj.kind} {obj.metadata.name}")
            obj.spec.template.spec.nodeSelector = parsed


class MetallbNativeManifest(Manifests):
    def __init__(self, charm, charm_config):
        manipulations = [
            ManifestLabel(self),
            ConfigRegistry(self),
            PatchNamespace(self),
            PatchNodeSelector(self),
        ]

        super().__init__("metallb", charm.model, "upstream/metallb-native", manipulations)
        self.charm_config = charm_config

    @property
    def config(self) -> Dict:
        """Returns config mapped from charm config and joined relations."""
        config = dict(**self.charm_config)
        for key, value in dict(**config).items():
            if value == "" or value is None:
                del config[key]  # blank out keys not currently set to something

        config["release"] = config.pop("metallb-release", None)
        return config
