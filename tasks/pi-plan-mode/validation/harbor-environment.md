# Harbor integration

The recorded validation used Harbor 0.23.0 and the pinned linux/amd64 Pi image.
Each trial requested 4 CPUs, 8192 MiB and no network. Successful results are in
[`e2e-evidence.json`](e2e-evidence.json); failed image setup attempts are not
behavioral reward-zero results.

## Optional registry mirror

`harbor_mirror.py` is an optional launcher for installations that cannot fetch
Harbor's kernel-probe image from Docker Hub. It checks the expected upstream
reference and substitutes the registry while retaining the exact digest. It
does not override capability detection, network isolation, user identities,
task settings or scoring, and is not included in the agent image.

Run it with the Python environment that has Harbor installed:

```bash
python3 tasks/pi-plan-mode/validation/harbor_mirror.py --help
```

Harbor's probe and egress-sidecar images must be available before starting an
offline trial. Any proxy, registry credentials or Buildx configuration belong
to the execution environment and must stay outside task artifacts. Record image
identities and tool versions when validating; do not publish container inspect
dumps or host-specific network configuration.
