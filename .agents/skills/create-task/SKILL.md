---
name: create-task
description: Create ai-infra-bench Harbor tasks from a concrete infrastructure problem, including the instruction, pinned environment, behavioral verifier, reference solution when available, and construction checks. Use for new benchmark tasks, not routine edits or post-rollout review.
---

# Create an ai-infra-bench Task

Build a self-contained task under `tasks/<task-id>/`. Start from the user's
observable problem and reuse the scope and settings already agreed in the
session. The repository uses single-step tasks, offline execution, shared
verification, and binary rewards; do not reopen those choices while scaffolding.

Read the current [task template and conventions](../../../templates/harbor-task/README.md)
before writing configuration. It is the maintained source for metadata, hardware,
time budgets, collection, validation layout, and image manifests. Copy
[`templates/harbor-task`](../../../templates/harbor-task/) rather than relying on
generic Harbor scaffold defaults.

## Define the contract and investigate history

For changes to an existing repository, establish the target behavior and exact
Base, then follow [references/upstream-history.md](references/upstream-history.md).
Read the supplied issue or PR and relevant later fixes, including unresolved
reports. Historical source informs the task; neither an upstream merge nor its
patch defines correctness. If research is unavailable, identify that limitation.

For vLLM, CUDA, Triton, native extensions, or collectives, read
[references/ai-infra-vllm-gpu.md](references/ai-infra-vllm-gpu.md). Apply the cutoff
and agent-visibility rules in the independent
[review rubric](../ai-infra-bench-task-review/references/review-rubric.md#5-audit-solvability-visibility-and-runtime-conditions).
These construction checks do not perform the independent review itself.

Write `instruction.md` as a developer request with the observable symptom or
feature, relevant inputs, supported modes, and behavior that must remain intact.
Do not reveal the reference fix, private helpers, hidden tests, or curation
process. Make `description` one concise sentence about the problem or requested
outcome; it is a website summary, not a diagnosis.

## Configure the task

Use the template's field order and current values:

- `[task]`: version `1.0.0`, no authors; keywords start with `vllm` followed by at
  most three topic keywords derived from the instruction and available Oracle.
  Do not add CPU/GPU or grading-method tags. The website skips the first keyword
  when displaying and searching topics.
- `[metadata]`: only `task_type` (`feature`, `bugfix`, or `performance`),
  `base_commit`, and `dependency_cutoff`.
- `[environment]`: 8 CPUs, 16384 MiB memory, 51200 MiB storage, runtime
  `no-network`, and `build_timeout_sec = 10800`. Keep a Dockerfile and omit
  `docker_image` from committed task configs. CPU tasks set `gpus = 0`; GPU
  tasks use `gpu_types = ["A100"]` and the required GPU count.
- `[agent].timeout_sec = 36000`; `[verifier].timeout_sec = 7200`.
- Omit `verifier.environment_mode` and `verifier.environment` for shared grading.
  Keep top-level `artifacts` equal to the task workdir and the standard
  `verifier.collect` hook with `timeout_sec = 300`.

The template contains the complete collector. After setting the workdir, Base,
and agent user, regenerate it rather than writing a different per-task script:

```bash
python3 tools/sync_collect_hooks.py
python3 tools/normalize_task_configs.py --check
```

Runtime assets and dependency-cutoff exceptions belong in
`environment/build-config.json`; use the existing
[all-in-one builder](../../../templates/vllm-harbor-all-in-one/README.md) when
applicable. Do not reintroduce removed metadata, hardware aliases, or evidence
summaries. Keep the initial-release version during editorial normalization;
identify development and validation snapshots by commits and file hashes.

## Build an offline environment

Install the real Base source and pinned semantic dependencies, together with
the agent's ordinary debugging and test tools. Keep task-specific tests,
solutions, control patches, and diagnostic reproducers out of agent-visible
filesystems and image layers. Preserve useful Base history while excluding
future source and answer-bearing objects or caches.

Preinstall the verifier's dependencies too. Shared verification uses the same
container after the agent finishes; it must not require runtime package/model
fetches or a separate verifier image. Supply private tests only at verification
time. Read-only harness files and candidate execution privileges still need
an explicit design; shared mode does not establish isolation by itself.

Check a fresh container as the actual agent user under the declared network
policy. Collect and run a relevant existing test using the installed interpreter
and normal paths. Distinguish Base behavior failures from missing imports,
fixtures, tools, hardware, or permissions. Rebuild affected native targets and
verify which libraries actually execute when applicable.

Retain the actual image ID and input-file hashes in `environment/image-manifest.json`
using the [minimal format](../../../templates/harbor-task/README.md#image-manifest).
Verify current hashes; never update them merely to make an old build look current.
Keep verbose build logs and package inventories with external run records.

## Implement behavioral verification

Establish [fixture reachability](../ai-infra-bench-task-review/references/review-rubric.md#8-verify-fixture-reachability)
before making a case affect reward. Use the smallest complete production boundary
that determines the required behavior. Different correct implementations must
pass, including ones with different private helpers or representations.

Use a pinned pytest or custom verifier appropriate to the task. Initialize
`/logs/verifier/reward.txt` to `0`, and write `1` only after all required behavioral
and completion checks succeed. Use absolute paths and preserve readable logs for
the actual Harbor host user. Candidate code exiting successfully, suppressing
assertions, or writing a success marker is not proof that checks completed.
Do not add an online judge or runtime `uvx` dependency to these offline tasks.

For Oracle-based tasks, provide `solution/oracle.patch` and executable
`solution/solve.sh`. Test the reference implementation against the contract,
including applicable regressions found during upstream research.

Only an explicitly accepted unsolved task may use
`"validation_mode": "verifier_only"` in `validation/ci-cases.json`. It omits the
unavailable Oracle and uses Base plus independent protocol/behavior controls.
Describe how a solver could reconstruct the missing implementation and what
full-task solvability remains unproven. Do not use this mode to conceal a
broken Oracle.

Declare control patches in `validation/ci-cases.json` with schema
`ai_infra_bench_validation_cases.v2`, their actual hashes and expected rewards,
and `patches/<name>.patch` paths. Set `apply_after = "oracle"` only for controls
that build on the Oracle. Put reusable probes in `validation/tools/` and their
outputs outside the task. Retain historical reports through Git, not a release
`history/` directory or evidence JSON.

## Validate and hand off

Run repository checks and the actual Harbor entrypoint. For ordinary CPU tasks:

```bash
python3 .github/scripts/task_ci.py validate <task-id>
python3 tools/sync_collect_hooks.py --check
python3 tools/normalize_task_configs.py --check
python3 tools/normalize_image_manifests.py --check
harbor run -p tasks/<task-id> -a nop --env docker --cpus limit --memory limit
harbor run -p tasks/<task-id> -a oracle --env docker --cpus limit --memory limit
```

For GPU execution use the configured provider and allocation described in
[GPU runner instructions](../../../.github/GPU-RUNNERS.md), and verify actual device
assignment. CPU CI adds a four-CPU override; formal task declarations remain at
eight CPUs. Do not copy the CI override into the task config or disable CPU/RAM
limits. Docker does not enforce the declared storage value as a disk quota.

Use `task_ci.py cases` and `prepare-case` to run the declared controls on their
correct bases. Base must receive zero for the target behavior; Oracle and
correct alternatives receive one; incorrect controls receive zero for their
intended violation. For `verifier_only`, omit the Oracle command and use the
approved controls, recording the missing full-solution evidence. Performance
checks require the declared device, measurement protocol, and adequate margin.

Verify both the agent-end snapshot and collector output under actual Harbor.
Keep commands, identities, rewards, failures, and limitations with the run
records. Update an existing task README if needed; do not add a new documentation
hierarchy or require a README solely to satisfy generic scaffolding instructions.

Hand the frozen candidate and construction results to `ai-infra-bench-task-review`
when independent review is requested. New model rollouts, publishing, or changes
to the agreed benchmark policy require their own task authorization.
