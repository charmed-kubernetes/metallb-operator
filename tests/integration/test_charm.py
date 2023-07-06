#!/usr/bin/env python3
# Copyright 2023 Stone
# See LICENSE file for licensing details.
import asyncio
import logging
from pathlib import Path

import aiohttp
import pytest
import yaml
from pytest_operator.plugin import OpsTest

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
    charm = await ops_test.build_charm(".")

    # Deploy the charm and wait for active/idle status
    await asyncio.gather(
        ops_test.model.deploy(
            charm, application_name=APP_NAME, trust=True, config={"namespace": NAMESPACE}
        ),
        ops_test.model.wait_for_idle(
            apps=[APP_NAME], status="active", raise_on_blocked=True, timeout=1500
        ),
    )


async def test_iprange_config_option(ops_test: OpsTest, client, ip_address_pool):
    # test that default option is applied correctly before changing
    pool_name = f"{ops_test.model_name}-{APP_NAME}"
    pool = client.get(ip_address_pool, name=pool_name, namespace=NAMESPACE)
    assert pool.spec["addresses"][0] == "192.168.1.240-192.168.1.247"

    app = ops_test.model.applications[APP_NAME]
    logger.info("Updating iprange ...")
    await app.set_config(
        {
            "iprange": "10.1.240.240-10.1.240.241",
        }
    )
    await ops_test.model.wait_for_idle(status="active", timeout=60 * 10)
    pool = client.get(ip_address_pool, name=pool_name, namespace=NAMESPACE)
    assert pool.spec["addresses"][0] == "10.1.240.240-10.1.240.241"


async def test_loadbalancer_service(ops_test: OpsTest, client, microbot_service_ip):
    logger.info("Testing microbot load balancer service")
    timeout = aiohttp.ClientTimeout(connect=30)
    async with aiohttp.request("GET", f"http://{microbot_service_ip}", timeout=timeout) as resp:
        logger.info(f"response: {resp}")
        assert resp.status == 200
