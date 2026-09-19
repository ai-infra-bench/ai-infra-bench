import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ci_gpu_docker import LeasedGpuDockerEnvironment


DEVICES = [
    "GPU-00000000-0000-0000-0000-000000000000",
    "GPU-00000000-0000-0000-0000-000000000001",
]
LABELS = {"io.ai-infra-bench.pool": "pool-id"}


class LeasedGpuDockerEnvironmentTests(unittest.TestCase):
    def test_capabilities_include_enforced_no_network(self):
        environment = object.__new__(LeasedGpuDockerEnvironment)
        environment._enable_egress_control = False
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
