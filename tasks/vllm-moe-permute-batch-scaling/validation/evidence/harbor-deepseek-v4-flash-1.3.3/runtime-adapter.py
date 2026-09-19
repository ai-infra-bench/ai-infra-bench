from harbor.environments.docker.docker import DockerEnvironment

class A100DockerEnvironment(DockerEnvironment):
    """Local Docker adapter; the task compose overlay reserves GPU 0."""
    @property
    def capabilities(self):
        return super().capabilities.model_copy(update={"gpus": True})

    def _validate_gpu_support(self):
        if self._effective_gpus != 1:
            raise RuntimeError("This local adapter requires exactly one GPU")
        import yaml
        overlay = yaml.safe_load(self._environment_docker_compose_path.read_text())
        devices = overlay['services']['main']['deploy']['resources']['reservations']['devices']
        if devices != [{'driver': 'nvidia', 'device_ids': ['0'], 'capabilities': ['gpu']}]:
            raise RuntimeError("Missing explicit A100 GPU 0 reservation")
        super()._validate_gpu_support()
