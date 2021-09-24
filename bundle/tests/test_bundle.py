import aiohttp


async def test_build_and_deploy(ops_test, test_helpers, rbac):
    # can't use the bundle because of:
    # https://github.com/juju/python-libjuju/issues/472
    # can't use ops_test.build_charms() because of:
    # https://github.com/canonical/charmcraft/issues/554
    controller_charm = await ops_test.build_charm("charms/metallb-controller")
    speaker_charm = await ops_test.build_charm("charms/metallb-speaker")
    controller = await ops_test.model.deploy(
        controller_charm,
        config={"iprange": "10.1.240.240-10.1.240.241"},
        resources={"metallb-controller-image": "metallb/controller:v0.9.3"},
    )
    speaker = await ops_test.model.deploy(
        speaker_charm,
        resources={"metallb-speaker-image": "metallb/speaker:v0.9.3"},
    )

    if rbac:

        def units_in_error(expect_error):
            def _predicate():
                if not (controller.units and speaker.units):
                    return False
                controller_status = controller.units[0].workload_status
                speaker_status = speaker.units[0].workload_status
                if expect_error:
                    # only error is allowed
                    return {"error"} == {controller_status, speaker_status}
                else:
                    # no error is allowed
                    return {"error"} ^ {controller_status, speaker_status}

            return _predicate

        # confirm units go to error if RBAC rules not in place
        await ops_test.model.block_until(units_in_error(True), timeout=5 * 60)
        # confirm adding RBAC rules enables units to resolve
        await test_helpers.apply_rbac_operator_rules()
        await controller.units[0].resolved(retry=True)
        await speaker.units[0].resolved(retry=True)
        # NB: This only blocks until the units are not in error state, but they
        # likely are in maintenance or executing instead. If we went straight to
        # the wait_for_idle below, it would immediately fail due to the previous
        # error states since the hooks haven't started the retry yet.
        await ops_test.model.block_until(units_in_error(False), timeout=5 * 60)

    await ops_test.model.wait_for_idle(wait_for_active=True, raise_on_blocked=True)
    # test metallb
    await test_helpers.metallb_ready()
    await test_helpers.deploy_microbot()
    svc_address = await test_helpers.svc_ingress("microbot-lb")
    timeout = aiohttp.ClientTimeout(connect=10)
    async with aiohttp.request("GET", f"http://{svc_address}", timeout=timeout) as resp:
        assert resp.status == 200
