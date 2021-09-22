import asyncio
import logging
import pytest


log = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def test_helpers(ops_test):
    return TestHelpers(ops_test)


class TestHelpers:
    def __init__(self, ops_test):
        self.ops_test = ops_test

    async def deploy_charms(self):
        # can't use the bundle because of:
        # https://github.com/juju/python-libjuju/issues/472
        charms = await self.ops_test.build_charms(
            "charms/metallb-controller", "charms/metallb-speaker"
        )
        controller = await self.ops_test.model.deploy(
            charms["metallb-controller"],
            config={"iprange": "10.1.240.240-10.1.240.241"},
            resources={"metallb-controller-image": "metallb/controller:v0.9.3"},
        )
        speaker = await self.ops_test.model.deploy(
            charms["metallb-speaker"],
            resources={"metallb-speaker-image": "metallb/speaker:v0.9.3"},
        )
        return controller, speaker

    async def kubectl(self, *cmd):
        rc, stdout, stderr = await self.ops_test.run(
            "microk8s",
            "kubectl",
            "-n",
            self.ops_test.model_name,
            *cmd,
        )
        assert rc == 0
        return stdout.strip()

    async def pods_ready(self, label, count):
        log.info(f"Waiting for {count} {label} pods to be ready")
        for attempt in range(60):
            status = await self.kubectl(
                "get",
                "pod",
                "-l",
                label,
                "-o",
                "jsonpath={.items[*].status.phase}",
            )
            status = status.split()
            log.info(f"Status: {status}")
            if status == ["Running"] * count:
                return
            else:
                await asyncio.sleep(2)
        else:
            raise TimeoutError(
                f"Timed out waiting for {count} {label} pods to be ready"
            )

    async def svc_ingress(self, svc_name):
        log.info(f"Waiting for ingress address for {svc_name}")
        for attempt in range(60):
            ingress_address = await self.kubectl(
                "get",
                "svc",
                svc_name,
                "-o",
                "jsonpath={.status.loadBalancer.ingress[0].ip}",
            )
            log.info(f"Ingress address: {ingress_address}")
            if ingress_address != "":
                return ingress_address
            else:
                await asyncio.sleep(2)
        else:
            raise TimeoutError(
                f"Timed out waiting for {svc_name} to have an ingress address"
            )

    async def metallb_ready(self):
        # wait for operator pods to be ready
        await self.pods_ready("operator.juju.is/target=application", 2)
        # wait for workload pods to be ready
        await self.pods_ready(
            "app.kubernetes.io/name in (metallb-controller,metallb-speaker)", 2
        )

    async def deploy_microbot(self):
        await self.kubectl("apply", "-f", "./docs/example-microbot-lb.yaml")
        await self.pods_ready("app=microbot-lb", 3)
