"""Allocate one explicit local GPU for Harbor's normal Docker lifecycle."""

import json
from pathlib import Path
import tempfile

from harbor.environments.docker.docker import DockerEnvironment
from harbor.models.task.config import NetworkMode, NetworkPolicy


class NvidiaDockerEnvironment(DockerEnvironment):
    def __init__(self, *args, gpu_devices="5", **kwargs):
        devices = str(gpu_devices).split(",")
        expected = kwargs["task_env_config"].gpus
        if len(devices) != expected or len(set(devices)) != expected:
            raise ValueError("explicit device count must match the task")
        self._gpu_overlay_dir = tempfile.TemporaryDirectory(prefix="session-harbor-gpu-")
        overlay = Path(self._gpu_overlay_dir.name) / "gpu.yaml"
        overlay.write_text(json.dumps({"services": {"main": {
            "shm_size": "2gb",
            "network_mode": "none",
            "deploy": {"resources": {"reservations": {"devices": [{
                "driver": "nvidia", "device_ids": devices, "capabilities": ["gpu"],
            }]}}},
        }}}))
        kwargs["extra_docker_compose"] = [*kwargs.get("extra_docker_compose", []), overlay]
        if kwargs.get("network_policy") is None:
            kwargs["network_policy"] = NetworkPolicy(network_mode=NetworkMode.NO_NETWORK)
        super().__init__(*args, **kwargs)

    @staticmethod
    def _requires_egress_control(**kwargs):
        # This offline task uses Docker's network namespace isolation directly.
        return False

    @property
    def capabilities(self):
        return super().capabilities.model_copy(update={"gpus": True, "disable_internet": True})

    async def _apply_network_policy(self, policy):
        if policy.network_mode != NetworkMode.NO_NETWORK:
            raise ValueError("this local adapter only supports an offline task")
