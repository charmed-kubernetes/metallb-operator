import asyncio
import logging
import yaml
from distutils.util import strtobool
from pathlib import Path

import pytest


log = logging.getLogger(__name__)


def pytest_addoption(parser):
    parser.addoption(
        "--rbac",
        nargs="?",
        type=strtobool,
        default=False,
        const=True,
        help="Whether RBAC is enabled and should be tested",
    )


@pytest.fixture
def rbac(request):
    return request.config.getoption("--rbac")


@pytest.fixture(scope="module")
def test_helpers(ops_test):
    return TestHelpers(ops_test)


class TestHelpers:
    def __init__(self, ops_test):
        self.ops_test = ops_test

    async def kubectl(self, *cmd):
        rc, stdout, stderr = await self.ops_test.run(
            "kubectl",
            "-n",
            self.ops_test.model_name,
            *cmd,
        )
        assert rc == 0, f"Command 'kubectl {' '.join(cmd)}' failed:\n{stderr}"
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

    async def apply_rbac_operator_rules(self):
        rbac_src_path = Path("./docs/rbac-permissions-operators.yaml")
        rbac_dst_path = self.ops_test.tmp_path / "rbac.yaml"
        rbac_rules = list(yaml.safe_load_all(rbac_src_path.read_text()))
        for subject in rbac_rules[1]["subjects"]:
            subject["namespace"] = self.ops_test.model_name
        rbac_dst_path.write_text(yaml.safe_dump_all(rbac_rules))
        await self.kubectl("apply", "-f", rbac_dst_path)

    async def deploy_microbot(self):
        await self.kubectl("apply", "-f", "./docs/example-microbot-lb.yaml")
        await self.pods_ready("app=microbot-lb", 3)
