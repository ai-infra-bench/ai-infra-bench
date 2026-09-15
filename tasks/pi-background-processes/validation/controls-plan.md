# Control matrix

`ci-cases.json` lists the negative controls below; CI runs Base and Oracle
implicitly. Every control is `solution/oracle.patch` with one deliberate
defect, so each rejection isolates a single contract clause. Expected reward
is the verifier's 0/1.

| Control | Defect | Expected | Harbor reward (2026-09-14, local arm64 image) | Rejecting layer |
|---|---|---|---|---|
| base | no extension | 0 | 0 | contract + lifecycle (`Tool bg_run not found`), PASS_TO_PASS skipped |
| oracle | reference implementation | 1 | 1 | all layers pass |
| control-killall-on-session-shutdown | `session_shutdown` kills every process | 0 | 0 | contract (new-session/fork survival, handover) |
| control-kill-direct-child-only | signals the child pid, never the group | 0 | 0 | contract (grandchildren) + lifecycle (exit, SIGTERM) |
| control-no-exit-hooks | no pi exit / signal handlers | 0 | 0 | lifecycle (orphans survive pi exit and SIGTERM); contract passes |
| control-in-memory-log | keeps every line in memory besides the file | 0 | 0 | contract (heap growth 76 MB vs 24 MB bound) |
| control-report-killed-before-group-gone | marks `killed` right after SIGTERM | 0 | 0 | contract (kill timing, cleanup, wake cases) |
| control-swallow-cleanup-failure | reports `failed: false` always | 0 | 0 | contract (cleanup) |
| control-never-trigger-turn | steer without `triggerTurn` | 0 | 0 | contract (idle exit wake, handover) |
| control-process-exit-zero-after-registration | `process.exit(0)` 50 ms after load | 0 | 0 | vitest exit status (unhandled exit in worker) + lifecycle; the JUnit inventory alone would have passed |
| control-stall-kills-instead-of-backgrounding | `bash` kills a silent command and reports a timeout instead of moving it to the background | 0 | 0 | contract (stall case: tool error instead of a backgrounded record) |
| control-normal-path-returns-json | `bash` returns the JSON record on the normal path and never raises the built-in exit/timeout errors | 0 | 0 | contract (normal-path case: `isError`, error wording) |
| control-backgrounded-no-output-wake | a backgrounded command never fires the `output` wake | 0 | 0 | contract (stall case: first wake is `["exit"]`, not `["output"]`) |
| control-forged-junit | writes a passing contract JUnit then exits | 0 | 0 | vitest exit status + lifecycle; the forged inventory passed `check_junit.py`, so exit status is a required part of the defense |

Correct alternative (`alternative-class-manager-sparse-index.patch`, expected
reward 1): class-based manager module, log store with a sparse line index, per-
process wake state, unconditional signal re-raise; derived from the grok-4.6
rollout submission with its SIGTERM deferral fixed. Harbor reward 1 (115 s).
Independent challenge (`independent_challenge.py` + `independent_probe.mjs`):
Oracle 8/8, alternative 8/8 (relative cwd + Unicode error line, intermittent
output stays foreground, paging past the end, bg_kill on a finished process).

All rows above were run through the full Harbor 0.22.0 entrypoint
(`task_ci.py prepare-case` -> `harbor run` -> `check-result`) on the local
linux/arm64 image `sha256:713cd734…`. Job logs: `~/ai-infra-scratch/harbor-jobs/`.
The x64 CI runner has not run them yet.

Rerun 2026-09-14 (after the first real-agent rollout, see
`rollout-2026-09-14-claude-code.md`): the verifier changed in three places
(runtime teardown no longer emits a process-level `quit`, `pidAlive` treats
zombies as gone, the in-image PASS_TO_PASS baseline is hash-pinned) and the
`bg_kill` sentence of `instruction.md` was corrected. All twelve cases were
rerun on the same image with `tools/local_task_validation.py`: base 0, oracle 1,
ten controls 0, no errored trials, 74 to 100 s per case. The rerun supersedes
the earlier note that the controls predated the last `test.sh` change.

Rerun 2026-09-14 (bash override added): the contract grew to 16 cases and the
matrix to 13 controls. All fifteen cases were rerun on the same image with
`tools/local_task_validation.py`: base 0, oracle 1, thirteen controls 0, no
errored trials, 73 to 101 s per case.

Rerun 2026-09-14 (coalescing case removed): contract 15 cases, 12 controls.
All fourteen cases rerun on the same image: base 0, oracle 1, twelve controls
0, no errored trials, 75 to 99 s per case.

Rerun 2026-09-14 (test.sh now snapshots the agent diff): fourteen cases, all match.

Rerun 2026-09-14 (semantic baseline pins + alternative case): fifteen cases
(base, oracle, alternative, twelve controls), all match, 67 to 115 s each.

Rerun 2026-09-14 (`allowed_failures` pin): `tests/baseline-pins.json` now also
lists the only cases the in-image baseline may mark as failed on Base (the
union of the arm64 and amd64 environmental failures), closing the residual
hole where a rewritten baseline could exempt up to six arbitrary cases. Only
the PASS_TO_PASS layer changed, so the rerun covered base, oracle, the
alternative, and the two controls that layer rejects
(`control-forged-junit`, `control-process-exit-zero-after-registration`):
see `e2e-evidence.json` `harbor_runs.allowed_failures_rerun`.
`validation/baseline_pin_forgery_check.py` reproduces the forgery check.

Text-only change 2026-09-14: `instruction.md` now states that a relative
`bg_run` `cwd` resolves against the session's working directory and the record
stores the absolute path (a behaviour the independent challenge already
relied on). No verifier or Oracle bytes changed, so no matrix rerun.

Image rebuild 2026-09-14 (template): the Dockerfile is now generated from
`templates/pi-harbor-node` (lock sha256 check, embedded baseline checker,
provenance labels; the installed software is unchanged) and the canonical image
was built with `build.py --platform linux/amd64`. Verifier and Oracle bytes did
not change, so only base and oracle were rerun on the new image through Harbor
(see `e2e-evidence.json` `harbor_runs.template_image_smoke`); the controls are
not affected by the image identity.

Rerun 2026-09-14 (style pass): the verifier TypeScript and Python files were
reformatted with pi's biome configuration and ruff (import order, two lint
fixes in `bg.lifecycle.test.ts`, `test.sh` now writes reward 0 when the
workspace is missing instead of continuing). No contract semantics changed;
the full fifteen-case matrix was rerun anyway on the arm64 image (all match)
and base/oracle on the canonical amd64 image (0 / 1). See `e2e-evidence.json`
`harbor_runs.style_pass_rerun`.
