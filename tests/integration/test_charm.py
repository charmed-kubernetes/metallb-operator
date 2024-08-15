#!/usr/bin/env python3
# Copyright 2023 Stone
# See LICENSE file for licensing details.
import datetime
import logging
from pathlib import Path

import aiohttp
import juju.application
import juju.unit
import pytest
import yaml
from lightkube.resources.core_v1 import Pod
from pytest_operator.plugin import OpsTest
from tenacity import after_log, retry, stop_after_delay, wait_fixed

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
NAMESPACE = "metallb-system-test"


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Build the charm-under-test and deploy it together with related charms.

    Assert on the unit status before any relations/configurations take place.
    """
    # Build and deploy charm from local source folder
    charm = next(Path().glob("metallb*.charm"), None)
    if not charm:
        logger.info("Building charm")
        charm = await ops_test.build_charm(".")

    # Deploy the charm and wait for active/idle status
    model = ops_test.model
    await model.deploy(
        charm.resolve(), application_name=APP_NAME, config={"namespace": NAMESPACE}
    ),
    await model.block_until(
        lambda: APP_NAME in model.applications,  # application is present
        lambda: model.applications[APP_NAME].status in ("active", "blocked"),
        timeout=1500,
    )
    await model.wait_for_idle(apps=[APP_NAME])
    metal_lb: juju.application.Application = model.applications[APP_NAME]
    if metal_lb.units[0].workload_status == "blocked":
        # The charm is blocked because it requires the --trust flag to be deployed
        assert "deploy with --trust" in metal_lb.units[0].workload_status_message
        await metal_lb.set_trusted(True)
        await model.wait_for_idle(apps=[APP_NAME], status="active")


async def test_iprange_config_option(ops_test: OpsTest, client, ip_address_pool, iprange):
    # test that default option is applied correctly before changing
    pool_name = f"{ops_test.model_name}-{APP_NAME}"
    pool = client.get(ip_address_pool, name=pool_name, namespace=NAMESPACE)
    assert pool.spec["addresses"][0] == "192.168.1.240-192.168.1.247"

    app = ops_test.model.applications[APP_NAME]
    logger.info("Updating iprange ...")
    await app.set_config(
        {
            "iprange": iprange,
        }
    )
    await ops_test.model.wait_for_idle(status="active", timeout=60 * 10)
    pool = client.get(ip_address_pool, name=pool_name, namespace=NAMESPACE)
    assert pool.spec["addresses"][0] == iprange


@pytest.mark.usefixtures("ops_test", "client")
async def test_loadbalancer_service(microbot_service_ip):
    logger.info("Testing microbot load balancer service")
    timeout = aiohttp.ClientTimeout(connect=30)
    async with aiohttp.request("GET", f"http://{microbot_service_ip}", timeout=timeout) as resp:
        logger.info(f"response: {resp}")
        assert resp.status == 200


@retry(stop=stop_after_delay(60 * 5), wait=wait_fixed(5), after=after_log(logger, logging.INFO))
def wait_for_new(client, begin, resource, *_, **kwargs):
    for obj in client.list(resource, **kwargs):
        if obj.metadata.creationTimestamp < begin:
            raise Exception(f"Found {resource} created at {obj.metadata.creationTimestamp}")


async def test_node_selector(ops_test: OpsTest, client):
    begin = datetime.datetime.now(tz=datetime.timezone.utc)
    extended = "kubernetes.io/os=linux kubernetes.io/arch=amd64"

    await ops_test.model.applications[APP_NAME].set_config({"node-selector": extended})
    await ops_test.model.wait_for_idle(status="active", timeout=60 * 5)
    wait_for_new(client, begin, Pod, namespace=NAMESPACE, labels={"app": "metallb"})
    for pod in client.list(Pod, namespace=NAMESPACE, labels={"app": "metallb"}):
        assert pod.spec.nodeSelector["kubernetes.io/arch"] == "amd64"
        assert pod.spec.nodeSelector["kubernetes.io/os"] == "linux"
