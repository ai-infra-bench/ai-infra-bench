"""Local Harbor adapter: bind one GPU and enforce network none for both phases."""
import json, os, re, hashlib, subprocess, fcntl, shutil
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
        mirror = self._prepare_storage()
        self._local_overlay.write_text('services:\n  main:\n    network_mode: none\n    shm_size: 1gb\n    tmpfs:\n      - /tmp:rw,exec,size=2g,mode=1777\n    volumes:\n      - '+str(mirror/'vllm')+':/workspace/repo/vllm\n      - '+str(mirror/'agent-cache')+':/home/agent/.cache\n      - '+str(mirror/'root-cache')+':/root/.cache\n    deploy:\n      resources:\n        reservations:\n          devices: !override\n            - driver: nvidia\n              capabilities: [gpu]\n              device_ids: '+json.dumps([device])+'\n')

    def _prepare_storage(self):
        """Keep large, isolated source copies off this host's full root disk."""
        root = Path(os.environ.get('PR64_STORAGE_ROOT', '/data/pr64-review-20260919/harbor-storage'))
        root.mkdir(parents=True, exist_ok=True)
        image = self.task_env_config.docker_image
        identity = subprocess.check_output(['docker', 'image', 'inspect', image, '--format', '{{.Id}}'], text=True).strip()
        base = root / hashlib.sha256(identity.encode()).hexdigest()
        base.mkdir(exist_ok=True)
        with (base/'lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not (base/'complete').exists():
                if (base/'vllm').exists():
                    shutil.rmtree(base/'vllm')
                container = subprocess.check_output(['docker', 'create', image], text=True).strip()
                try:
                    subprocess.run(['docker', 'cp', '-a', container+':/workspace/repo/vllm', str(base/'vllm')], check=True)
                finally:
                    subprocess.run(['docker', 'rm', container], check=True, stdout=subprocess.DEVNULL)
                (base/'complete').write_text(identity)
        mirror = root / ('phase-'+self.session_id)
        mirror.mkdir(exist_ok=False)
        subprocess.run(['cp', '-a', '--reflink=auto', str(base/'vllm'), str(mirror/'vllm')], check=True)
        # docker cp exports root-owned host files even with -a here. Match the
        # image's agent ownership so Oracle/agent edits are actually applied.
        subprocess.run(['chown', '-R', '1000:1000', str(mirror/'vllm')], check=True)
        (mirror/'agent-cache').mkdir()
        os.chown(mirror/'agent-cache', 1000, 1000)
        (mirror/'root-cache').mkdir(mode=0o700)
        self._phase_storage = mirror
        return mirror

    async def stop(self, *args, **kwargs):
        await super().stop(*args, **kwargs)
        if hasattr(self, '_phase_storage') and self._phase_storage.exists():
            shutil.rmtree(self._phase_storage)

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
