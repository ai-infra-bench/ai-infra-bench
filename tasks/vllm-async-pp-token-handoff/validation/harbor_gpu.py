"""Local Harbor 0.22 Docker adapter with explicit NVIDIA device allocation.

Stock Harbor Docker does not advertise or allocate GPUs in this version. This
adapter keeps the normal Harbor agent/verifier lifecycle and adds a compose
GPU reservation. It does not modify the task, scorer, or rewards.
"""
import json
from pathlib import Path
import tempfile

from harbor.environments.docker.docker import DockerEnvironment


class NvidiaDockerEnvironment(DockerEnvironment):
    def __init__(self, *args, gpu_devices='1,3', **kwargs):
        devices = str(gpu_devices).split(',')
        expected = kwargs['task_env_config'].gpus
        if len(devices) != expected or len(set(devices)) != expected:
            raise ValueError('explicit GPU device count must match task requirements')
        self._gpu_overlay_dir = tempfile.TemporaryDirectory(prefix='pr75-harbor-gpu-')
        overlay = Path(self._gpu_overlay_dir.name)/'gpu.yaml'
        # JSON is valid YAML; quote device IDs to preserve their string type.
        overlay.write_text(json.dumps({'services':{'main':{
            'shm_size':'2gb',
            'deploy':{'resources':{'reservations':{'devices':[{
                'driver':'nvidia','device_ids':devices,'capabilities':['gpu'],
            }]}}},
        }}}))
        kwargs['extra_docker_compose'] = [*kwargs.get('extra_docker_compose',[]), overlay]
        super().__init__(*args, **kwargs)

    @property
    def capabilities(self):
        return super().capabilities.model_copy(update={'gpus':True})
