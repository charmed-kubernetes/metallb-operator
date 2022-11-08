import logging

import aiohttp


log = logging.getLogger(__name__)


async def test_build_and_deploy(ops_test, test_helpers, rbac):
    rc, stdout, stderr = await ops_test.run(
        "juju", "model-config", "-m", ops_test.model_full_name
    )
    log.info(stdout)
    # can't use the bundle because of:
    # https://github.com/juju/python-libjuju/issues/472
    # can't use ops_test.build_charms() because of:
    # https://github.com/canonical/charmcraft/issues/554
    controller_charm = await ops_test.build_charm("charms/metallb-controller")
    speaker_charm = await ops_test.build_charm("charms/metallb-speaker")
    controller = await ops_test.model.deploy(
        controller_charm,
        config={"iprange": "10.1.240.240-10.1.240.241"},
        resources={"metallb-controller-image": "metallb/controller:v0.12"},
        trust=True
    )
    speaker = await ops_test.model.deploy(
        speaker_charm,
        resources={"metallb-speaker-image": "metallb/speaker:v0.12"},
        trust=True
    )

    if rbac:

        def units_in_error(expect_error):
            def _predicate():
                no = "no " if not expect_error else ""
                if not (controller.units and speaker.units):
                    s = "s" if not (controller.units or speaker.units) else ""
                    log.info(f"Waiting for {no}error: missing unit{s}")
                    return False
                controller_status = controller.units[0].workload_status
                speaker_status = speaker.units[0].workload_status
                log.info(
                    f"Waiting for {no}error: {controller_status}, {speaker_status}"
                )
                if expect_error:
                    # only error is allowed
                    return {"error"} == {controller_status, speaker_status}
                else:
                    # no error is allowed
                    return {"error"} ^ {controller_status, speaker_status}

            return _predicate

        log.info("Testing RBAC failure and recovery")
        # confirm units go to error if RBAC rules not in place
        await ops_test.model.block_until(
            units_in_error(True), timeout=5 * 60, wait_period=1
        )
        # confirm adding RBAC rules enables units to resolve
        log.info("Applying RBAC rules and retrying hooks")
        await test_helpers.apply_rbac_operator_rules()
        await controller.units[0].resolved(retry=True)
        await speaker.units[0].resolved(retry=True)
        # NB: This only blocks until the units are not in error state, but they
        # likely are in maintenance or executing instead. If we went straight to
        # the wait_for_idle below, it would immediately fail due to the previous
        # error states since the hooks haven't started the retry yet.
        await ops_test.model.block_until(
            units_in_error(False), timeout=5 * 60, wait_period=1
        )

    await ops_test.model.wait_for_idle(wait_for_active=True, raise_on_blocked=True)


async def test_microbot_lb(ops_test, test_helpers):
    # test metallb
    log.info("Testing LB with microbot")
    await test_helpers.metallb_ready()
    await test_helpers.deploy_microbot()
    svc_address = await test_helpers.svc_ingress("microbot-lb")
    timeout = aiohttp.ClientTimeout(connect=10)
    async with aiohttp.request("GET", f"http://{svc_address}", timeout=timeout) as resp:
        assert resp.status == 200

    for unit in ops_test.model.units.values():
        rc, stdout, stderr = await ops_test.run(
            "juju", "show-status-log", "-m", ops_test.model_full_name, unit.name
        )
        log.info(stdout)
