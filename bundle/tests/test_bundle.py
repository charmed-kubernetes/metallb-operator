import aiohttp


async def test_build_and_deploy(ops_test, test_helpers, rbac):
    # can't use the bundle because of:
    # https://github.com/juju/python-libjuju/issues/472
    charms = await ops_test.build_charms(
        "charms/metallb-controller", "charms/metallb-speaker"
    )
    controller = await ops_test.model.deploy(
        charms["metallb-controller"],
        config={"iprange": "10.1.240.240-10.1.240.241"},
        resources={"metallb-controller-image": "metallb/controller:v0.9.3"},
    )
    speaker = await ops_test.model.deploy(
        charms["metallb-speaker"],
        resources={"metallb-speaker-image": "metallb/speaker:v0.9.3"},
    )

    if rbac:
        # confirm units go to error if RBAC rules not in place
        await ops_test.model.wait_for_idle(raise_on_error=False, raise_on_blocked=True)
        assert controller.units[0].workload_status == "error"
        assert speaker.units[0].workload_status == "error"
        # confirm adding RBAC rules enables units to resolve
        await test_helpers.apply_rbac_operator_rules()
        await controller.units[0].resolved(retry=True)
        await speaker.units[0].resolved(retry=True)
        await ops_test.model.block_until(
            lambda: "error"
            not in (
                controller.units[0].workload_status,
                speaker.units[0].workload_status,
            )
        )

    await ops_test.model.wait_for_idle(wait_for_active=True, raise_on_blocked=True)
    # test metallb
    await test_helpers.metallb_ready()
    await test_helpers.deploy_microbot()
    svc_address = await test_helpers.svc_ingress("microbot-lb")
    timeout = aiohttp.ClientTimeout(connect=10)
    async with aiohttp.request("GET", f"http://{svc_address}", timeout=timeout) as resp:
        assert resp.status == 200
