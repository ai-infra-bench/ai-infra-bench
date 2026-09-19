"""Local Harbor adapter: bind one GPU and enforce network none for both phases."""
import json, os, re
from pathlib import Path
from harbor.environments.docker.docker import DockerEnvironment
from harbor.models.task.config import NetworkMode

class LocalGpuDocker(DockerEnvironment):
    @staticmethod
    def _requires_egress_control(**kwargs):
        return False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        device = os.environ['PR64_GPU_UUID']
        if not re.fullmatch(r'GPU-[0-9a-f-]{36}', device):
            raise ValueError('bad GPU UUID')
        if self._effective_gpus != 1:
            raise ValueError('task must request one GPU')
        self._gpu_uuid = device
        self._local_overlay = self.trial_paths.trial_dir/f'local-{self.session_id}.yaml'
        self._local_overlay.parent.mkdir(parents=True,exist_ok=True)
        self._local_overlay.write_text('services:\n  main:\n    network_mode: none\n    shm_size: 1gb\n    deploy:\n      resources:\n        reservations:\n          devices: !override\n            - driver: nvidia\n              capabilities: [gpu]\n              device_ids: '+json.dumps([device])+'\n')

    @property
    def _uses_compose(self):
        return True

    @property
    def capabilities(self):
        return super().capabilities.model_copy(update={'gpus':True,'disable_internet':True})

    @property
    def _docker_compose_paths(self):
        return [*super()._docker_compose_paths,self._local_overlay]

    def validate_network_policy_support(self, network_policy=None):
        policy=network_policy or self.network_policy
        if policy.network_mode != NetworkMode.NO_NETWORK:
            raise ValueError('this adapter only supports network none')

    async def _apply_network_policy(self, network_policy):
        self.validate_network_policy_support(network_policy)

    async def start(self, *args, **kwargs):
        await super().start(*args, **kwargs)
        result=await self.exec('nvidia-smi --query-gpu=uuid --format=csv,noheader')
        if result.return_code != 0 or set(result.stdout.split()) != {self._gpu_uuid}:
            raise RuntimeError('incorrect GPU visibility')
