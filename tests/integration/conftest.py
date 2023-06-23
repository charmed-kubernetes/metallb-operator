import logging
from pathlib import Path

import pytest
import pytest_asyncio
from lightkube import Client, codecs
from lightkube.generic_resource import create_namespaced_resource
from lightkube.resources.apps_v1 import Deployment
from lightkube.resources.core_v1 import Service

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def client():
    return Client()


@pytest.fixture(scope="module")
def ip_address_pool():
    return create_namespaced_resource(
        group="metallb.io",
        version="v1beta1",
        kind="IPAddressPool",
        plural="ipaddresspools",
    )


@pytest_asyncio.fixture(scope="function")
async def microbot_service_ip(client):
    logger.info("Creating microbot resources ...")
    path = Path("tests/data/microbot.yaml")
    for obj in codecs.load_all_yaml(path.read_text()):
        if obj.kind == "Namespace":
            namespace = obj.metadata.name
        client.create(obj)

    client.wait(Deployment, "microbot-lb", for_conditions=["Available"], namespace=namespace)
    logger.info("Microbot deployment is now available")

    svc = client.get(Service, name="microbot-lb", namespace="microbot")
    ingress_ip = svc.status.loadBalancer.ingress[0].ip

    yield ingress_ip

    logger.info("Deleting microbot resources ...")
    for obj in codecs.load_all_yaml(path.read_text()):
        client.delete(type(obj), obj.metadata.name, namespace=obj.metadata.namespace)
