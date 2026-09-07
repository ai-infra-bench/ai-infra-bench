# Docker build and baseline validation

> **Historical evidence only.** The instruction, verifier, task configuration,
> or environment changed during the current hardening pass. These results do
> not validate the current executable snapshot and must be regenerated.

## 2026-09-03 verifier false-positive repair

The first revised verifier counted connector readiness callbacks. An Opus-5
candidate reduced those callbacks to constant work but still removed and
reinserted every blocked request through the ordinary waiting queue on every
idle tick. It incorrectly received reward 1. The final verifier therefore
instruments both externally triggered readiness work and ordinary waiting-queue
removals, while continuing to grade completion promotion, FCFS order,
unfinished accounting, and abort behavior.

Four fresh, network-disabled containers produced:

```text
Base:                                                   0
Oracle:                                                 1
Frozen callback-only Opus-5 patch:                      0
Independent private-queue-name variant of production:  1
```

The Base performed 120 readiness callbacks for 24 unchanged waiters over five
idle rounds. The frozen incomplete candidate also performed 120 ordinary queue
pops and is now rejected. The positive control renames the private deferred
queue throughout production source and still passes, demonstrating that the
verifier does not require the Oracle's `skipped_waiting` name. Its patch
SHA-256 is
`7fd2cba20a9ae07dfdc66788b5eaaa21751300dd9f246e375c09b577ceef9156`.

## Target

- Remote host: `bm-baai-dx-zone1-d-a100-40g-2-106`
- Workload accelerator: CPU, x86_64
- Validation hardware: physical GPU index 2, NVIDIA A100-SXM4-40GB
- Work directory: `/data/ai-infra-bench/survey-builds/vllm-pr-35781`
- Image tag: `ai-infra-bench/vllm-pr-35781:base`
- Docker endpoint: `unix:///data/yaoyaoyao/pr34183-cuda-build/docker.sock`
- Docker data root: `/data/yaoyaoyao/pr34183-cuda-build/docker-data`

All Docker commands explicitly export the endpoint. Runtime commands use
`--network none`.

## Source and image acquisition

The official source API resolved base commit
`d88f28da05b12bc7d63ebe3dcedf445ecb274343` to Git tree
`037cc4e534167733500093aa225de6ab64a1028e`. Its codeload archive was
independently downloaded and measured as:

```text
size: 30558740 bytes
sha256: 7808db147610c4413d1d813d559eeb22dcbf37e39285746092c508c680cf3fee
```

This exactly matches the archive previously bundled by the audit task; the
environment does not depend on that branch's copy.

The digest-pinned v0.17.1 x86_64 CPU image was absent from the isolated daemon.
Cold pull completed in 186.81 seconds. Inspection of the unmodified image
reported:

```text
Python 3.12.13
vLLM 0.17.1
PyTorch 2.10.0+cpu
torch.version.cuda = None
torch.cuda.is_available() = False
base inspect Size = 1074060265 bytes
```

Cold pull time is recorded separately from Dockerfile build time.

## Build

The isolated daemon has no bridge. The host therefore served the already
SHA-verified archive through a temporary server bound only to
`127.0.0.1:35781`. The Dockerfile verified the same hash again. No proxy
credential entered a build argument, task file, image layer or log.

```bash
export DOCKER_HOST=unix:///data/yaoyaoyao/pr34183-cuda-build/docker.sock
docker build --network host --no-cache \
  --build-arg VLLM_SOURCE_URL=http://127.0.0.1:35781/vllm-codeload.tar.gz \
  -f environment/Dockerfile \
  -t ai-infra-bench/vllm-pr-35781:base \
  environment
```

The build succeeded on its first attempt:

```text
elapsed: 216.17 seconds (3 minutes 36.17 seconds)
image ID: sha256:fa99603d9410446e82aa395d1842e0d18f36e622d82510e9dcbc345dc3456d1e
docker inspect Size: 1421570193 bytes
docker images virtual size: 5.86GB
published registry digest: not available (local validation image only)
```

The loopback server PID and exact command were checked before it was stopped.

## Runtime provenance

The CPU runtime was started with `--network none`:

```json
{"candidate_source": "/app/vllm/__init__.py", "native_extension": "/app/vllm/_C.abi3.so", "python": "3.12.13", "torch": "2.10.0+cpu", "torch_cuda_available": false, "workload_accelerator": "cpu"}
```

Additional assertions passed:

- one synthetic Git commit;
- canonical Git tree `037cc4e534167733500093aa225de6ab64a1028e`;
- no Git remote, tag or dirty candidate file;
- source and `vllm._C` both resolve under `/app`;
- outbound TCP probe failed with `connect_ex=101`.

The official CPU image's `_C_AVX2` module fails a direct Python import because
it has no `PyInit__C_AVX2` entry point. The same failure occurs in the
unmodified official image, so it was not introduced by the candidate overlay.
The scheduler baseline succeeds, but this is not a full CPU inference smoke.

## Declared hardware path

The workload is intentionally CPU-only. A separate container was nevertheless
started with `--gpus device=2`. Inside the container `nvidia-smi` saw exactly:

```text
0, NVIDIA A100-SXM4-40GB, GPU-3815a178-ad22-4b81-5669-0533760a7e6b
```

The UUID matches host physical GPU index 2. PyTorch remained `2.10.0+cpu` with
`torch.cuda.is_available() == false`, so the hardware check does not misstate
the task as a CUDA workload. The CPU image reports `NVIDIA_VISIBLE_DEVICES=void`
even though the runtime-mounted `nvidia-smi` sees the requested device;
therefore UUID comparison, rather than that environment variable, is the
authoritative validation evidence.

## Deterministic baseline reproduction

The script uses upstream `tests.v1.core.utils` and the production Scheduler and
MockKVConnector. It creates 24 requests blocked on asynchronous remote KV and
runs five idle scheduler rounds with no completion event.

```json
{"baseline_bug_reproduced": true, "expected_legacy_callbacks": 120, "has_separate_skipped_waiting_queue": false, "idle_rounds": 5, "ordinary_waiting_queue_size": 24, "remote_kv_callbacks": 120, "requests": 24}
```

All three repeated runs produced exactly the same JSON. This demonstrates the
base defect without relying on the original two-GPU P/D throughput result:

- every idle round revisits every blocked request: `24 * 5 = 120` callbacks;
- all 24 blocked requests churn through the ordinary waiting queue;
- no separate skipped/blocked queue exists.

This is environment-ready and a stable structural baseline. It is not a
complete verifier for FCFS/priority ordering, promotion, abort, recovery,
statistics, or regression behavior.

## Shared-verifier audit

The audit branch currently declares `environment_mode = "shared"`. Its grader
runs from `/app`, sets `PYTHONPATH=/app`, applies hidden upstream test patches
into the candidate-controlled `/app/tests` tree, and invokes candidate test
utilities and `conftest.py`. `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` does not prevent
candidate `sitecustomize.py`, import-path manipulation, standard-library
monkeypatching, or modification of upstream test helpers.

Consequently the existing shared verifier is not a strong trust boundary even
though `/tests` itself is mounted separately. Release hardening should use an
independent verifier image/process, start Python in isolated mode before adding
only reviewed production paths, keep upstream test files/helpers in a trusted
copy, and integrity-check grader/scorer/required/heldout assets. This Dockerfile
is an agent environment and baseline package; it does not claim to resolve that
verifier risk.

Raw logs and evidence remain under
`/data/ai-infra-bench/survey-builds/vllm-pr-35781/` on the validation host.
> **Historical evidence only.** The instruction, verifier, task configuration,
> or environment changed during the current hardening pass. These results do
> not validate the current executable snapshot and must be regenerated.
