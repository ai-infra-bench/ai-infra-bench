# A100 CI runners

Run four independent GitHub Actions runner services on one machine, sharing a host-managed pool of four A100 GPU UUIDs. A runner is an execution slot, not a fixed GPU. Tasks request one GPU by default in their task definition, or explicitly request two or four. Keep `topology` and `gpus` equal and retain the existing `gpu,a100,harbor` labels and `[1,2,4]` topology contract.

## Host setup

Use a dedicated CI account with Docker access, four separate runner installation/work directories and four separate `HOME`/`DOCKER_CONFIG` directories. Install Python 3.12, Harbor 0.22.0, Git, jq, Docker Engine, Buildx, Docker Compose supporting `!override` (2.24.4 or newer), NVIDIA drivers and NVIDIA Container Toolkit. Put the Harbor virtual environment on each runner's persistent PATH so both `python` and `harbor` resolve correctly. If the environment is shared, keep its pinned dependencies administrator-managed to avoid simultaneous installation updates.

Image builds use Docker's default build network unless the host sets `AI_INFRA_BUILD_NETWORK`. The prepared A100 host uses `host` because its default `docker0` bridge was missing during setup. Test containers still use Harbor's Compose networks. If registry access requires a proxy, configure it on the host's Docker daemon. For downloads during image builds, configure standard HTTP/HTTPS proxy variables in the runner service environment; the validation script forwards them as predefined Docker build arguments without requiring Dockerfile changes. Keep proxy credentials in restricted host configuration files, outside the repository. Docker Hub image pulling through the prepared host's daemon proxy has been verified.

Configure every runner with the same `AI_INFRA_GPU_POOL_CONFIG`, pointing to an administrator-managed JSON file such as `/data/ai-infra-ci/gpu-pool.json`:

```json
{
  "gpu_uuids": ["GPU-<physical-card-0-uuid>", "GPU-<physical-card-1-uuid>", "GPU-<physical-card-2-uuid>", "GPU-<physical-card-3-uuid>"],
  "state_dir": "/data/ai-infra-ci/pool"
}
```

Read UUIDs with `nvidia-smi --query-gpu=index,uuid,name --format=csv,noheader`. The state directory must be writable by the CI account and reside on a local filesystem supporting `flock`. All four runners must use exactly the same configuration and lock directory. Do not remove lock files, change the device list or reorder UUIDs while jobs are running.

Download and checksum-verify the Linux x64 runner distribution using GitHub's repository Settings → Actions → Runners page. Register each installation with a unique name such as `a100-pool-0` through `a100-pool-3` and labels `gpu,a100,harbor`. Install each service with `svc.sh install <ci-user>`. Persist `HOME`, `DOCKER_CONFIG`, `PATH` and `AI_INFRA_GPU_POOL_CONFIG` in the runner environment/service configuration before starting it. A registration token expires after one hour; do not commit it or save it in service environment files.

## Execution and cleanup

`run_task_validation.sh` preserves the ordinary Docker backend for CPU tasks. For GPU tasks, each Harbor validation case runs under `gpu_pool.py`. Image builds and pulls happen before GPU acquisition. A lease is released between cases, allowing other jobs to make progress.

The pool acquires all requested GPU locks before starting Harbor. A waiter holding the admission lock blocks new allocations while active leases drain, so a four-GPU request can proceed once running cases finish. Requests are not promised strict FIFO order. A queued acquisition times out after two hours; GitHub's overall job timeout also includes builds and queue time.

`ci_gpu_docker:LeasedGpuDockerEnvironment` adds GPU capability to Harbor 0.22.0's Docker backend, applies the assigned UUIDs to the main service's device reservation, sets container-local CUDA ordinals and verifies visible UUIDs before starting the agent. Task definitions must request the same number of GPUs as the lease. GPU sidecar allocation is not supported by this adapter and must not be added independently to task Compose files.

Each container gets pool and GPU-slot labels. On normal completion or cancellation, the supervisor stops remaining child processes and removes labeled containers before releasing its locks. Harbor inherits the lease descriptors: killing only the supervisor does not release devices while Harbor can still create containers. Before reusing a released lease, the next job removes stale containers carrying that pool's corresponding slot labels. Other containers are not pruned. Leaked networks and images are not automatically pruned; review disk usage separately.

This is cooperative resource scheduling for reviewed CI code, not a security boundary against hostile workflows. The runner's Docker access can control the host daemon. Keep GPU PR execution behind the repository's `task-validation` environment review and review workflow changes before approving execution. Do not mount the Docker socket or host GPU device directories into task containers. Ensure other users and services do not use the four reserved CI GPUs; the pool does not manage external workloads.

## Validation

Run the CPU-only allocation and result parsing tests:

```bash
python3 -m unittest discover -s .github/scripts/tests -v
bash -n .github/scripts/run_task_validation.sh
python3 .github/scripts/task_ci.py validate
```

To validate real hardware, run as the CI user with the same environment as the service. The image must already exist locally and provide Python, CUDA and PyTorch. Each output path must be new:

```bash
python .github/scripts/tests/smoke_gpu.py --image <local-cuda-pytorch-image> --counts 1,1,1,1 --parallel --output /data/ai-infra-ci/smoke-single
python .github/scripts/tests/smoke_gpu.py --image <local-cuda-pytorch-image> --counts 2,2 --parallel --output /data/ai-infra-ci/smoke-double
python .github/scripts/tests/smoke_gpu.py --image <local-cuda-pytorch-image> --counts 4 --output /data/ai-infra-ci/smoke-four
python .github/scripts/tests/smoke_gpu_cleanup.py --image <local-cuda-pytorch-image> --output /data/ai-infra-ci/smoke-cleanup
```

These are infrastructure smoke tasks outside the benchmark corpus. They run actual Harbor verifier trials and CUDA tensor operations, verify rewards using the CI result checker and retain UUID/timing evidence. They do not establish correctness or performance of a benchmark task. After the branch is merged and runners are online, perform a GitHub Actions run on an actual A100 task to complete remote acceptance; CPU tasks continue to use GitHub-hosted runners.

Harbor 0.22.0 stores per-trial rewards in `stats.evals.*.reward_stats.reward`, while its `metrics` contains aggregate means. The result checker reads the per-trial rewards and requires exactly one completed, error-free trial with the expected reward; older direct reward metrics remain supported.
