import json
from pathlib import Path
import sys
import types
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakeCapabilities:
    def __init__(self, **values):
        defaults = {
            "gpus": False,
            "disable_internet": False,
            "network_allowlist": False,
            "network_allowlist_hostnames": False,
            "network_allowlist_wildcard_hostnames": False,
            "network_allowlist_ipv4_addresses": False,
            "network_allowlist_ipv6_addresses": False,
            "network_allowlist_ipv4_cidrs": False,
            "network_allowlist_ipv6_cidrs": False,
            "dynamic_network_policy": False,
        }
        defaults.update(values)
        self.__dict__.update(defaults)

    def model_copy(self, update):
        return FakeCapabilities(**(self.__dict__ | update))


class FakeDockerEnvironment:
    @property
    def capabilities(self):
        return FakeCapabilities()


docker_module = types.ModuleType("harbor.environments.docker.docker")
docker_module.DockerEnvironment = FakeDockerEnvironment
config_module = types.ModuleType("harbor.models.task.config")
config_module.NetworkMode = types.SimpleNamespace(NO_NETWORK="no-network")
module_stubs = {
    "harbor": types.ModuleType("harbor"),
    "harbor.environments": types.ModuleType("harbor.environments"),
    "harbor.environments.docker": types.ModuleType("harbor.environments.docker"),
    "harbor.environments.docker.docker": docker_module,
    "harbor.models": types.ModuleType("harbor.models"),
    "harbor.models.task": types.ModuleType("harbor.models.task"),
    "harbor.models.task.config": config_module,
}
saved_modules = {name: sys.modules.get(name) for name in module_stubs}
sys.modules.update(module_stubs)
try:
    from ci_gpu_docker import LeasedGpuDockerEnvironment
finally:
    for name, module in saved_modules.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


DEVICES = [
    "GPU-00000000-0000-0000-0000-000000000000",
    "GPU-00000000-0000-0000-0000-000000000001",
]
LABELS = {"io.ai-infra-bench.pool": "pool-id"}


class LeasedGpuDockerEnvironmentTests(unittest.TestCase):
    def test_capabilities_include_enforced_no_network(self):
        environment = object.__new__(LeasedGpuDockerEnvironment)
        capabilities = environment.capabilities
        self.assertTrue(capabilities.gpus)
        self.assertTrue(capabilities.disable_internet)
        self.assertFalse(capabilities.network_allowlist)
        self.assertFalse(capabilities.dynamic_network_policy)

    def test_no_network_overlay_resets_task_networks(self):
        overlay = LeasedGpuDockerEnvironment._gpu_overlay_contents(
            DEVICES, LABELS, True
        )
        self.assertIn("    networks: !reset []\n", overlay)
        self.assertIn("    network_mode: none\n", overlay)
        self.assertIn(f"      NVIDIA_VISIBLE_DEVICES: {json.dumps(','.join(DEVICES))}\n", overlay)

    def test_public_overlay_keeps_compose_networking(self):
        overlay = LeasedGpuDockerEnvironment._gpu_overlay_contents(
            DEVICES, LABELS, False
        )
        self.assertNotIn("network_mode:", overlay)
        self.assertNotIn("networks:", overlay)


if __name__ == "__main__":
    unittest.main()
