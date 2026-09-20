# Harbor Task Template

Copy this directory to `tasks/<task-id>/` when materializing a validated task.

Set `[task].version` to `"1.0.0"` for the initial release and omit `authors`.
Use a concise, single-sentence `description` of the observable problem or
requested outcome; avoid revealing the diagnosis or reference implementation.
Set `[agent].timeout_sec = 36000` (10 hours) for the benchmark agent budget.
Start `keywords` with the project (`"vllm"`, or `"pi"` for the agent-harness tasks on earendil-works/pi) and add at most three topic keywords
based on the instruction and reference solution, when available. Do not use
CPU/GPU tags, including compound tags such as `gpu-worker`. Use keywords for
subsystem and topic labels instead of a separate `subsystems` field.
The website derives the repository (and the `agent_harness` domain of pi tasks) from that leading keyword and skips it when displaying or searching topics.

Keep only `task_type`, `base_commit`, and `dependency_cutoff` in `[metadata]`:
Harbor 0.22 does not preserve custom fields in `[task]`. Use `feature` for added
capabilities, `bugfix` for incorrect behavior
or stalled progress, and `performance` for latency, throughput, or memory-use
improvements. Classify by the requested outcome, even when the solution is a
refactor. Store optional runtime assets and dependency-cutoff exceptions in
`environment/build-config.json`, image identity in `environment/image-manifest.json`,
and any `validation_mode` override in `validation/ci-cases.json`.
Follow the [image manifest format](#image-manifest) below.

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
solution/oracle.patch
tests/test.sh
validation/ci-cases.json
validation/patches/
```

Follow the [validation layout](#validation-layout) below. Approved `verifier_only`
tasks omit the unavailable Oracle files.

Use Harbor's default shared verifier: omit `[verifier].environment_mode` and
do not define `[verifier.environment]`. Set `[verifier].timeout_sec = 7200`
(2 hours). The verifier runs in the agent's container and sees its filesystem
changes.
Task tests are supplied after the agent phase; they must not be baked into the
agent image. Shared verification is not a clean environment or automatic
protection against candidate code executed by the verifier.

Every task sets top-level `artifacts` to its complete `environment.workdir`,
including the checkout's Python, Rust, CUDA, build files, and new files. Harbor
collects this snapshot after the agent finishes and before verification, and
saves it under `<jobs_dir>/<job>/<trial>/artifacts/` with the source path mirrored
inside it. This preserves the agent's final submission even when the container
is deleted. It does not enable a separate verifier or capture later changes
made by the verification scripts.

CI sets `artifacts = []` only in its temporary task copies to avoid accumulating
full checkout snapshots. Task validation, image publication, and GPU smoke CI
do not upload artifacts. Formal evaluation configs retain complete snapshots
and the standard collector; GitHub Actions execution logs remain available.

Every task also has a self-contained `[[verifier.collect]]` hook with
`timeout_sec = 300`. It runs as the task's agent user, before tests are uploaded,
and writes these files to `/logs/artifacts/` for Harbor 0.22 to collect. They are
saved under `<trial>/artifacts/logs/artifacts/` on the host:

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

## Validation layout

Keep only `ci-cases.json`, `patches/`, and optional reusable `tools/` under
`validation/`. Use schema `ai_infra_bench_validation_cases.v2`; each case records
its name, `patch` as `patches/<name>.patch`, `patch_sha256`, `expected_reward`, and
optional `apply_after` (`base` by default, or `oracle`). Preserve the declared
patch base when preparing or checking a control. The scorer does not consume
these control patches.

The default validation mode runs Base, Oracle, and the declared controls.
Approved unsolved tasks set `"validation_mode": "verifier_only"` in
`ci-cases.json`; they run Base and controls without claiming an Oracle pass.
Record the missing full-solution validation explicitly in review/run results.

Keep results, review reports, and raw logs with CI or Harbor run records outside
the task. Do not recreate an evidence summary, `history/`, or Markdown reports
inside `validation/`. Use Git history to retrieve earlier records. Reusable
tools must write outputs to an explicit directory outside the task; some probes
require a disposable task container or GPU and must not run directly on the host.

## Image manifest

`environment/image-manifest.json` contains the retained `image_id` and a `files`
mapping from paths relative to `environment/` to SHA-256 values. Always record
`Dockerfile`, the dependency lock (`lock/requirements.txt` for Python targets, `lock/package-lock.json` for Node targets), and `lock/manifest.json`; additional input
files use the same mapping. The source revision and cutoff remain in `task.toml`
and the hashed lock manifest.

Only special builds need a `build` object, with the actual `dockerfile`,
`parent_image_id`, or non-default `args`. An incremental recipe must also have
its hash in `files`. Keep tags, registry references, timestamps, package
inventories, and validation conclusions with external build/run records.

```bash
python3 tools/normalize_image_manifests.py
python3 tools/normalize_image_manifests.py --check
```

Both commands verify recorded hashes against current files. They do not refresh
stale hashes or change image IDs. Resolve mismatches against the actual build;
matching file hashes alone do not establish a successful build or verification.
