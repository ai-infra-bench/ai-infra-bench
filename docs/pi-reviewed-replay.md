# Curator preparation and regrading

`pi-subagent-live-messaging` needs an explicitly reviewed interface and scenario profile for **each
materialized submission**, including Base, Oracle and known controls. No profile
is shipped by default. An ordinary standalone Harbor Oracle run therefore stops
with `integration_needed`; it does not establish an Oracle pass or feature failure.

`validation/ci-cases.json` explicitly opts this task into `reviewed_replay` for
Base, Oracle and every declared control. It pins the runner and each case's
binding, scenario and curator evidence by hash. Generic CI uses that catalog to
dispatch reviewed replay; unknown submissions have no catalog fallback.
`task_ci.py validate pi-subagent-live-messaging` still checks static declarations,
patch hashes and image inputs only. It does **not** run profile preparation or
establish a behavioral pass. Do not change `expected_reward` values or switch to
`verifier_only` to hide an integration failure.

## Standalone Docker / Harbor replay

`replay_reviewed.py` supplies the curator stage both for explicit local use and
for the task's opt-in CI catalog.
It needs Python 3.11+, a local immutable task image ID, Docker and Harbor.
Provide the task revision, reviewed adapters, evidence and a new output directory:

```bash
python3 -I validation/tools/replay_reviewed.py \
  --task /path/to/pi-subagent-live-messaging \
  --image sha256:REPLACE_WITH_ACTUAL_64_HEX_IMAGE_ID \
  --oracle --profile-id oracle-reviewed-1 \
  --binding /curator/adapters/interface.py \
  --scenario /curator/adapters/scenario.py \
  --review-evidence /curator/review.json \
  --output /curator/runs/oracle-reviewed-1 --dry-run
```

Replace the image placeholder with its real ID. Run the script by its absolute
path or from the task directory. `--dry-run` checks inputs and prints their hashes
without calling Docker/Harbor or creating the output. Remove it to execute.
Select exactly one of `--base`, `--oracle`, or `--submission /path/to/full.patch`.
Submission patches apply to Base by default; add `--after-oracle` only when that
is the reviewed patch base. Verify a declared control's manifest hash first.
The tool does not discover cases or infer patch bases from filenames.

The runner freezes a task copy, applies its solution as the task's unprivileged
agent user in an offline preparation container, prepares the explicit profile,
exports readable manifest/adapters, and removes that container. It then starts
one Harbor trial from the same image and deterministic patch inputs (`nop` for
Base, `oracle` for patch application). The scorer verifies that the second
materialization matches the reviewed content. No solver/model agent is launched.
This patch replay does not restore arbitrary ignored files from an old candidate
snapshot; use the manual frozen-snapshot path below when those files matter.

`replay.json`, logs, the prepared task and Harbor outputs remain under `--output`.
Runner exit 0 means one scored trial completed and its collected reward agrees
with the grading status; read `reward` to distinguish feature pass (1) and failure
(0). Runner exit 2 means preparation, integration or execution did not complete.
Public CPU CI passes `--cpus limit --memory limit --override-cpus 4 --delete
--no-artifacts`: the same 4-CPU and configured memory limits apply to preparation,
Harbor receives the explicit resource and cleanup flags, and only the disposable
task omits its top-level workspace archive. Logs and normal verifier collection
remain available. The canonical task's resource declarations are unchanged.
No retry occurs. A `STOP_REQUESTED` file in that output directory or SIGINT/SIGTERM
stops command dispatch and cleans up the preparation container; retain partial
evidence before starting another job. On error/stop, the runner also inspects
Compose containers and removes only exact IDs whose working directory is under
this run's jobs directory or whose bind mount points into one of its recorded
trial directories. It records project labels, ownership proof and resource/network
settings. Containers without proof remain untouched; the record does not claim
global cleanup. No name-prefix deletion or Docker prune is used.

The runner rehashes the copied curator inputs and prepared task at the end,
including on failure. A mismatch invalidates completion and returns exit 2;
`replay.json` retains before/after hashes and the observed trial reward separately.

## Prepare one reviewed submission

1. Make a disposable task copy outside the checkout and retain the exact image
   identity. Materialize the chosen submission inside that image before profiling.
   For a declared control, verify its `patch_sha256` and honor `apply_after` in
   `validation/ci-cases.json` (`base` when omitted). For a recovered candidate,
   preserve its full workspace snapshot, ignored files and installed dependencies;
   a source patch alone is not the complete identity. Never run candidate Git
   hooks or candidate Python as root.
2. Stop candidate processes. Review its public tool interface, transport and size
   policy. Prepare two trusted Python adapter files in curator storage outside
   `/workspace/pi`, exporting `Binding` and `Scenario`. Review adapters for
   fidelity: they translate calls/observations and exercise real resources; they
   must not supply missing messaging behavior. Do not import candidate Python or
   derive adapter selection from a candidate-owned file.
3. Record actual review evidence in a JSON object outside the task, for example
   `{"reviewer":"actual reviewer", "evidence":"path/to/actual-review.md",
   "submission":"immutable snapshot or control identity"}`. Those strings are
   provenance; the tool does not independently establish their truth.
4. Run the tool from the same reviewed task revision. The example below assumes
   the disposable task is `/curator/task` and the **final materialized** submission
   is `/workspace/pi` in the grading image:

   ```bash
   python3 -I /curator/task/validation/tools/prepare_profile.py \
     --repo /workspace/pi --tests /curator/task/tests \
     --profile-id reviewed-submission-1 \
     --interface /curator/adapters/interface.py \
     --scenario /curator/adapters/scenario.py \
     --review-evidence /curator/review.json
   ```

   This copies the explicitly supplied adapters and writes `tests/profile.json`
   in the disposable task. It does not execute the adapters, apply a patch, run
   tests, start Harbor, or launch models. Keep generated files out of the source
   task and solver-visible image layers.

   Even the reference requires explicit files, after confirming its interface
   and transport are appropriate for this submission:

   ```python
   # /curator/adapters/interface.py
   from binding import Binding
   ```

   ```python
   # /curator/adapters/scenario.py
   from scenario import Scenario
   ```

## Regrade exactly those bytes

The orchestration must supply that prepared `tests/` tree as root-owned,
non-writable-by-candidate `/tests` **after the agent phase**, then invoke the
normal grading entrypoint against the same frozen `/workspace/pi`. The grader
seals its harness before validation. A curator can also check an already sealed
mount without scoring or refreshing anything:

```bash
python3 -I /curator/task/validation/tools/prepare_profile.py \
  --check --repo /workspace/pi --tests /tests
```

Exit 0 means the content identity matches; it is not a behavioral pass. Exit 2
means integration is still needed. Both preparation and `--check` emit the
manifest to stdout; retain it with external run records if needed.

Use a no-op agent when regrading an already materialized candidate snapshot.
Do not profile Base and then run Oracle's patch application: that changes the
workspace and correctly invalidates the profile. A host checkout lacking the
image's `node_modules` likewise does not match. Each control gets its own
profile; sharing adapters is allowed only after review, sharing workspace hashes
is not. Any change to candidate files, scorer files or adapters requires preparing
and reviewing the corresponding identity again. `--check` never updates hashes.

The profile includes every workspace entry except `.git` metadata, including
ignored files and `node_modules`; symlinks bind their text rather than external
target contents. It rejects special files and detects changes observed during two
content scans. Keep the workspace quiescent: this is not a filesystem lock, and
external symlink targets still depend on runtime isolation.

Read `/logs/verifier/grading-status.json` with the normal grader artifacts:

| Status | Meaning |
| --- | --- |
| `integration_needed`, no reward files | Missing/stale profile or unsupported adaptation; unscored. |
| `scored`, reward 0 | The selected profile ran but required behavior/completion failed. Inspect case evidence. |
| `scored`, reward 1 | All required cases completed and passed under this profile. |
| `scoring_error` | Grader infrastructure failed; do not call this a candidate feature defect. |

Retain actual Harbor trial IDs, errors, profile and executable hashes, case
results and image identity outside the task. Direct container grading or a
successful `--check` does not cover Harbor artifact transfer or reward collection.
Missing reward must remain an integration failure in the job results, never be
coerced to numeric zero by a CI wrapper.

Small JSON scenario and review inputs may be stored directly in the CI manifest as
`{"content": {...}, "sha256": "..."}`. Hashes cover UTF-8 JSON serialized with
`json.dumps(content, indent=2)` and a trailing newline. CI materializes these inputs
for the existing replay runner and removes the temporary files afterward. Executable
adapters and runners remain explicit, hashed files. Detailed review reports and
run results are retained outside the task; only input identity metadata is needed here.
