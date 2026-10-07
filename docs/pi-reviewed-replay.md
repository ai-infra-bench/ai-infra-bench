# Curator preparation and regrading

Plan Mode uses a reviewed UI profile for each materialized submission, including
Base, Oracle and controls. No generated profile is shipped in the source task.
A standalone unprepared Harbor run stops with `integration_needed` and no reward.
This is an integration failure, not a candidate feature failure.

The current implementation lives in
`tasks/pi-plan-mode/validation/tools/replay_reviewed.py` and
`tasks/pi-plan-mode/tests/ui_profile.py`. These instructions describe those tools;
they do not claim that other Pi tasks supply equivalent profile tools.

## Declared CI cases

`validation/ci-cases.json` opts Plan Mode into `reviewed_replay`. It pins the runner
and each case's binding, scenario and review evidence. The catalog covers Base,
Oracle and every declared control; unknown submissions have no fallback binding.
Small scenario and evidence objects are serialized as indented JSON plus a final
newline and pinned by SHA-256. They record curator input provenance, not proof
that their descriptions are true or that behavior passed.

Run from the repository root with an actual immutable local image ID:

```bash
python3 .github/scripts/task_ci.py run-reviewed-case \
  --task pi-plan-mode --case oracle \
  --image sha256:REPLACE_WITH_ACTUAL_64_HEX_IMAGE_ID \
  --output /curator/runs/plan-oracle --override-cpus 4
```

The output directory must not already exist. The runner copies the task, applies
the selected patch as `pi-agent` in an offline preparation container, writes a
profile for that materialization, and removes the preparation container. Harbor
then materializes the same patch from the same image and runs the normal verifier.
The CI route checks the collected reward against the case's expected reward.
`task_ci.py validate pi-plan-mode` checks static inputs only; `prepare-case` alone
does not perform UI integration and is not the scoring route for this task.

## A new submission

Review the candidate's visible controls before observing outcomes. Supply exact
labels for selector actions, or explicit visible labels and keys for supported
custom UI. See [Plan Mode bindings](pi-plan-mode-ui-bindings.md). Do not try
choices until one yields the expected state.

Invoke the task runner directly with Python 3.11+, Docker and Harbor installed:

```bash
python3 tasks/pi-plan-mode/validation/tools/replay_reviewed.py \
  --task /checkout/tasks/pi-plan-mode \
  --image sha256:REPLACE_WITH_ACTUAL_64_HEX_IMAGE_ID \
  --submission /curator/submission.patch --profile-id reviewed-submission-1 \
  --binding /curator/ui-actions.json \
  --scenario /curator/scenario.json --review-evidence /curator/review.json \
  --output /curator/runs/reviewed-submission-1 \
  --cpus limit --memory limit --override-cpus 4 --delete --no-artifacts
```

Select exactly one of `--base`, `--oracle` and `--submission`. A submission applies
to Base unless `--after-oracle` is explicit. The scenario and evidence must be
nonempty JSON objects; record the reviewed source identity and visible-control
basis. The scenario is provenance for the fixed verifier suite, not executable
code that supplies candidate behavior. The runner does not recover ignored files
or arbitrary changes from an old workspace archive; patch replay is suitable only
when it faithfully materializes the reviewed submission.

The profile binds both candidate-editable trees (the plan extension and coding
agent tests), every verifier file, and the binding file. Other source and runtime
dependencies are immutable in the declared image and checked by the task scope
verifier. Symlinks are represented by their link text. Generated verifier staging,
Python cache directories, and the profile itself are excluded from their respective
inventories. The runner records the immutable image ID; it is supplied by the
trusted orchestrator rather than discovered from inside the container.

The root verifier copies and seals `/tests` after the agent phase, checks the
profile before creating a reward, then runs the unchanged behavioral assertions.
Any candidate, verifier or binding change requires a newly reviewed profile.
Missing or stale profiles leave `grading-status.json` with `integration_needed`
and no reward files. A valid profile allows scoring: `scored` with reward 0 means
required behavior or suite completion failed; reward 1 means all cases passed.
Unsupported UI needs additional integration review before a meaningful score.

The prepared task, profile, `replay.json`, and Harbor logs remain under `--output`.
A successful runner exit means one scored trial completed, including reward 0;
the generic CI wrapper additionally enforces the declared expected reward.
An exception or missing reward is a failed replay and must never be coerced to 0.
The `--delete` flag requests Harbor container cleanup. Preparation containers are
removed in `finally`; interruption of Harbor itself follows Harbor's own cleanup.
CPU CI uses four CPUs and the task's declared memory in both stages. The disposable
copy alone omits the top-level workspace archive with `--no-artifacts`; normal
verifier collection remains enabled.

## Build inputs and validation records

Plan Mode retains its task-local frozen `environment/Dockerfile`, template, lock,
and minimal `image-manifest.json`. The obsolete task-local generator, builder,
author matrix and evidence collector have been removed: they depended on metadata
and manifest fields that the shared task contract no longer has. Use the checked-in
Dockerfile as the build input, as normal Harbor/CI provisioning does. Its historical
header identifies its template origin; there is no supported local regeneration
command. Changes to environment inputs require a reviewed rebuild and new hashes.

For a retained image, the supported checks are:

```bash
python3 .github/scripts/task_ci.py validate pi-plan-mode
python3 .github/scripts/task_ci.py env-key --task pi-plan-mode --platform linux/amd64
python3 .github/scripts/task_ci.py image-check --task pi-plan-mode --image sha256:REPLACE_WITH_ACTUAL_64_HEX_IMAGE_ID
python3 .github/scripts/task_ci.py cases --task pi-plan-mode
```

Run the declared cases with `run-reviewed-case` as above. Keep the prepared task,
Harbor results, profile, and `replay.json` together outside the source task. These
records contain the image identity, exact candidate/verifier/binding hashes and
actual collected reward. Inspect the case summaries and raw JUnit reports beside
the reward; a static validation result does not establish behavioral success.
