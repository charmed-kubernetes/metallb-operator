#!/usr/bin/env python3
"""Speaker component for the MetalLB bundle."""

import logging
import os
from base64 import b64encode

from oci_image import OCIImageResource, OCIImageResourceError

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus

import utils

logger = logging.getLogger(__name__)


class MetalLBSpeakerCharm(CharmBase):
    """MetalLB Speaker Charm."""

    _stored = StoredState()

    def __init__(self, *args):
        """Charm initialization for events observation."""
        super().__init__(*args)
        if not self.unit.is_leader():
            self.unit.status = ActiveStatus()
            return
        self.image = OCIImageResource(self, "metallb-speaker-image")
        self.framework.observe(self.on.install, self._on_start)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.leader_elected, self._on_start)
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade)
        self.framework.observe(self.on.remove, self._on_remove)
        # -- initialize states --
        self._stored.set_default(k8s_objects_created=False)
        self._stored.set_default(started=False)
        self._stored.set_default(
            secret=b64encode(utils._random_secret(128).encode("utf-8")).decode("utf-8")
        )
        # -- base values --
        self._stored.set_default(namespace=os.environ["JUJU_MODEL_NAME"])

    def _on_start(self, event):
        """Occurs upon install, start, or upgrade of the charm."""
        if self._stored.started:
            return
        self.unit.status = MaintenanceStatus("Fetching image info")
        try:
            image_info = self.image.fetch()
        except OCIImageResourceError:
            logging.exception("An error occured while fetching the image info")
            self.unit.status = BlockedStatus("Error fetching image information")
            return

        if not self._stored.k8s_objects_created:
            self.unit.status = MaintenanceStatus(
                "Creating supplementary " "Kubernetes objects"
            )
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

    def _on_remove(self, event):
        """Remove artifacts created by the K8s API."""
        self.unit.status = MaintenanceStatus(
            "Removing supplementary " "Kubernetes objects"
        )
        utils.remove_k8s_objects(self._stored.namespace)
        self.unit.status = MaintenanceStatus("Removing pod")
        self._stored.started = False
        self._stored.k8s_objects_created = False

    def set_pod_spec(self, image_info):
        """Set pod spec."""
        self.model.pod.set_spec(utils.get_pod_spec(image_info, self._stored.secret))


if __name__ == "__main__":
    main(MetalLBSpeakerCharm)
