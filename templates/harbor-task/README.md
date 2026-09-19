# Harbor Task Template

Copy this directory to `tasks/<task-id>/` when materializing a validated task.

Set `[task].version` to `"1.0.0"` for the initial release and omit `authors`.
Set `[agent].timeout_sec = 36000` (10 hours) for the benchmark agent budget.
For vLLM tasks, start `keywords` with `"vllm"` and add at most three topic keywords
based on the instruction and reference solution, when available. Do not use
CPU/GPU tags, including compound tags such as `gpu-worker`. Use keywords for
subsystem and topic labels instead of a separate `subsystems` field.

Keep only `task_type`, `base_commit`, and `dependency_cutoff` in `[metadata]`:
Harbor 0.22 does not preserve custom fields in `[task]`. Use `feature` for added
capabilities, `bugfix` for incorrect behavior
or stalled progress, and `performance` for latency, throughput, or memory-use
improvements. Classify by the requested outcome, even when the solution is a
refactor. Store optional runtime assets and dependency-cutoff exceptions in
`environment/build-config.json`, image identity in `environment/image-manifest.json`,
and any `validation_mode` override in `validation/ci-cases.json`.

Declare hardware with Harbor's `[environment].gpus` and `gpu_types` fields.
All tasks declare `cpus = 8`, `memory_mb = 16384` (16 GiB), and
`storage_mb = 51200` (50 GiB).
CI invokes Harbor with `--cpus limit --memory limit` so the declared CPU and
memory values become container limits. CPU task CI additionally uses
`--override-cpus 4` for standard GitHub-hosted runners; GPU CI and formal
benchmark runs keep the declared eight-CPU budget. Runner capacity must support the request;
these limits do not reserve physical cores or enforce Docker disk quotas.
CPU tasks set `gpus = 0` and omit `gpu_types`; GPU tasks set a positive GPU count
and `gpu_types = ["A100"]`. The current CI pool supports 1, 2, or 4 A100 GPUs.
Do not add `environment_profile`, `accelerator`, or a
top-level `topology` field; CI and the website derive hardware from the official
resource fields.

Include `environment/Dockerfile` and omit `environment.docker_image` from the
checked-in task config; CI injects the image it built or pulled into the run's
temporary config. Set `environment.build_timeout_sec = 10800` (3 hours) for
Harbor-managed environment build/start. This does not time-limit the separate
Docker build performed by CI before Harbor starts. Keep
`environment.network_mode = "no-network"` as the runtime baseline; omitting it
defaults to public network access, and agent/verifier overrides only apply
during their respective execution phases.

The included `task.toml` defines benchmark-specific metadata and Harbor resource requirements. Add:

```text
instruction.md
environment/Dockerfile
environment/lock/
solution/solve.sh
tests/test.sh
tests/required/
tests/heldout/
```

Use Harbor's default shared verifier: omit `[verifier].environment_mode` and
do not define `[verifier.environment]`. Set `[verifier].timeout_sec = 7200`
(2 hours). The verifier runs in the agent's container and sees its filesystem
changes.

Every task sets top-level `artifacts` to its complete `environment.workdir`,
including the checkout's Python, Rust, CUDA, build files, and new files. Harbor
collects this snapshot after the agent finishes and before verification, and
saves it under `<jobs_dir>/<job>/<trial>/artifacts/` with the source path mirrored
inside it. This preserves the agent's final submission even when the container
is deleted. It does not enable a separate verifier or capture later changes
made by the verification scripts.

Every task also has a self-contained `[[verifier.collect]]` hook with
`timeout_sec = 300`. It runs as the task's agent user, before tests are uploaded,
and writes these files to `/logs/artifacts/` for Harbor 0.22 to collect:

- `solution.patch`: binary-capable diff from the fixed `metadata.base_commit`,
  including agent commits and staged/unstaged tracked changes.
- `untracked-files.tar.gz` and `untracked-paths.bin`: untracked, non-ignored
  files and their NUL-delimited names, including spaces and newlines safely.
- `git-status.txt`, `base-commit.txt`, and `head-commit.txt`: collection context.
- `collection-status.txt`: `complete` after all outputs are published; `failed`
  on a handled error, or `incomplete` if collection is interrupted abruptly.

The patch plus untracked archive complements the full workspace snapshot;
ignored build outputs and Git metadata remain in that snapshot. Collection is
best-effort: missing Git objects, unreadable files, concurrent writes, or a
timeout can prevent a usable incremental archive. A complete status records
successful command execution, not an atomic snapshot of concurrent processes.

After changing a task's workdir, base commit, or agent user, synchronize its hook:

```bash
python3 tools/sync_collect_hooks.py
python3 tools/sync_collect_hooks.py --check
```

This embeds the collector in each task config; it does not depend on a host
script being installed in the agent container or on access to `/tests`.

Keep configs in reading order: top-level schema/artifacts, task identity,
metadata, environment, agent, verifier, collection hooks, then optional CI
validation settings. Environment fields run from workdir/OS through resources,
network, and build timeout. Execution sections list user/network before timeout;
collection hooks list service/user/timeout before the command.

```bash
python3 tools/normalize_task_configs.py
python3 tools/normalize_task_configs.py --check
```

The normalizer preserves values, comments, and multiline commands, checks parsed
TOML equivalence before writing, and is idempotent. Hook synchronization also
applies this ordering.

Reference-solution identifiers and held-out test details should remain in curator-only storage until the task is released. The agent environment must contain only the clean base state and offline dependencies.
