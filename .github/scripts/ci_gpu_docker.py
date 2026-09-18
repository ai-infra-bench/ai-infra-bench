"""Harbor 0.22 Docker backend for GPUs leased by gpu_pool.py."""

import json
import os
from pathlib import Path
import re

from harbor.environments.docker.docker import DockerEnvironment


class LeasedGpuDockerEnvironment(DockerEnvironment):
    def __init__(self, *args, **kwargs):
        self._leased_devices = os.environ.get("AI_INFRA_GPU_UUIDS", "").split(",")
        if (
            not self._leased_devices
            or any(not re.fullmatch(r"GPU-[0-9a-f-]{36}", device) for device in self._leased_devices)
            or len(set(self._leased_devices)) != len(self._leased_devices)
        ):
            raise ValueError("start this backend through gpu_pool.py with valid GPU leases")
        self._pool_labels = json.loads(os.environ["AI_INFRA_GPU_LABELS"])
        if "io.ai-infra-bench.pool" not in self._pool_labels:
            raise ValueError("missing GPU pool cleanup labels")
        super().__init__(*args, **kwargs)
        if self._effective_gpus != len(self._leased_devices):
            raise ValueError("task GPU count does not match its allocated devices")
        self._gpu_overlay = self.trial_paths.trial_dir / "ci-gpu.compose.yaml"
        self._gpu_overlay.parent.mkdir(parents=True, exist_ok=True)
        # !override replaces any task-authored GPU reservation instead of merging
        # an extra device request that could expose cards outside the lease.
        self._gpu_overlay.write_text(
            "services:\n  main:\n"
            "    gpus: !reset []\n"
            "    devices: !reset []\n"
            "    device_cgroup_rules: !reset []\n"
            "    privileged: false\n"
            f"    labels: {json.dumps(self._pool_labels)}\n"
            "    environment:\n"
            f"      NVIDIA_VISIBLE_DEVICES: {json.dumps(','.join(self._leased_devices))}\n"
            f"      CUDA_VISIBLE_DEVICES: {json.dumps(','.join(str(i) for i in range(len(self._leased_devices))))}\n"
            "    deploy:\n      resources:\n        reservations:\n"
            "          devices: !override\n"
            "            - driver: nvidia\n"
            f"              device_ids: {json.dumps(self._leased_devices)}\n"
            "              capabilities: [gpu]\n"
        )

    @property
    def capabilities(self):
        return super().capabilities.model_copy(update={"gpus": True})

    @property
    def _docker_compose_paths(self) -> list[Path]:
        return [*super()._docker_compose_paths, self._gpu_overlay]

    async def start(self, *args, **kwargs):
        await super().start(*args, **kwargs)
        # Validate actual container visibility, including task-authored overrides.
        result = await self.exec("nvidia-smi --query-gpu=uuid --format=csv,noheader")
        actual = set((result.stdout or "").split())
        if result.return_code != 0 or actual != set(self._leased_devices):
            await self.stop(delete=True)
            raise RuntimeError(f"container GPU visibility mismatch: {actual}")
