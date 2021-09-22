import asyncio

import aiohttp


async def test_bundle(ops_test, test_helpers):
    await ops_test.run("microk8s", "enable", "rbac")
    controller, speaker = await test_helpers.deploy_charms()
    await ops_test.model.wait_for_idle(raise_on_error=False, raise_on_blocked=True)
    # confirm units go to error if RBAC rules not in place
    assert controller.units[0].workload_status == "error"
    assert speaker.units[0].workload_status == "error"
    # confirm adding RBAC rules enables units to resolve
    await test_helpers.kubectl("apply", "-f", "./docs/rbac-permissions-operators.yaml")
    await controller.units[0].resolved(retry=True)
    await speaker.units[0].resolved(retry=True)
    # FIXME need to wait for hooks to start going again, but fixed sleep sucks
    await asyncio.sleep(2)
    await ops_test.model.wait_for_idle(wait_for_active=True, raise_on_blocked=True)
    # test metallb
    await test_helpers.metallb_ready()
    await test_helpers.deploy_microbot()
    svc_address = await test_helpers.svc_ingress("microbot-lb")
    timeout = aiohttp.ClientTimeout(connect=10)
    async with aiohttp.request("GET", f"http://{svc_address}", timeout=timeout) as resp:
        assert resp.status == 200
