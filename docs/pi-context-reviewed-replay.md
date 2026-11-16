# Pi Context Management validation

The task now has one public configuration, capacity and pagination contract.
Run ordinary Harbor Base, Oracle and declared controls; new submissions need no
curator adapter, source inspection, or candidate-specific fixture calibration.
The same verifier and scenario inputs apply to every submission.

## Validated offline execution profile

The accepted Harbor 0.22 validation used an explicit Docker network override.
For prepared Base, Oracle and control tasks running with the `nop` agent, append
`--extra-docker-compose tools/pi-context-validation-network.yaml` to the existing
validation command. This file reproduces the accepted override byte for byte;
it does not change task inputs, candidate preparation or scoring. The path must
be readable on the host launching Harbor. For remote execution, transfer the
file with the validation inputs and pass its path on that host.

This profile is for offline verification, not online solver/model generation.
For each run, retain Docker inspection showing network mode `none` and container
observations showing only loopback and no external gateway, together with the
formal run's input identities and results. A `no-network` declaration in
`task.toml` alone does not establish that isolation. The previous default
deny-all proxy did not establish equivalent isolation; delivering this override
does not repair Harbor's default deny-all proxy. The Context public offline
validation runner now supplies this override automatically; actual isolation and
collection still require execution evidence.

## Public offline validation entrypoint

`.github/scripts/run_task_validation.sh` supplies this profile automatically for
Context Base, Oracle and ordinary declared controls on the CPU Docker path. A
missing profile or a `reviewed_replay` case fails explicitly instead of bypassing
isolation. Other tasks and online solver rollouts do not inherit the override.

The public CPU CI entrypoint retains its four-CPU override and 16 GiB limit.
Formal validation retains the task's eight CPUs and 16 GiB. Record these runs
separately, along with the actual Docker network and resource observations,
verifier output, reward, collection status and cleanup evidence. CI preparation
omits the full checkout archive; formal validation must retain that archive and
the standard collection hook. A missing reward is an execution/collection
failure to diagnose, not a behavioral zero or evidence of a network defect.

## Behavioral contract and observation

Configuration uses Pi extension flags: `--context-reminder-tokens`,
`--context-rollover-tokens` and `--context-response-headroom`. Capacity uses Pi's
existing `estimateTokens` semantics on current-window messages and normal setup,
as stated in the instruction. This replaces the former choice of unrelated
estimators and full-input/growth scopes. The model still chooses its working
notes; storage, history IDs and page sizes remain implementation choices.

Reminders are real Pi custom messages (`context_capacity_reminder`) containing
JSON text with remaining capacity and model guidance. A protected native module
preloaded before candidate code installs read-only public callbacks after the
candidate. An external Node inspector samples those callbacks, and the parent
binds each observed context to the actual HTTP payload from the real provider
adapter. Typed reminders must also appear in that actual request; `/event` is
only diagnostic. Tests never supply the candidate's reminders or reset logic.

History pagination uses `cursor` and `next_cursor`. Non-null cursor values are
passed back unchanged; absent/null ends traversal. Repeated opaque stateful
cursors and finite empty pages are allowed: traversal must still reach every
matching original. Search/read tool calls must not shift away older matches.
Full history and notes may
use lossless JSON; escaped complete originals remain valid, while summaries,
rewrites and truncated records do not.

Real Pi handles tool batches, sessions, HTTP providers, input queues and state.
Tests observe full-batch completion, the next actual request, saved notes and
selected original records. Base fails for absent features; a successful process
exit without the required trajectory cannot earn a positive reward. The trusted
parent owns scoring while candidate Pi executes as the agent user.

The previous reviewed-adapter workflow evaluated an earlier, more permissive
contract. Retain its frozen task, adapters and original results when inspecting
historical submissions. Those scores do not qualify a submission against this
revision's new public interfaces. Do not silently retrofit old candidate code or
reinterpret an old run as a new generation.

Keep actual rewards, exact image/task hashes and full trajectory/source artifacts
with external execution records. Scorer unit tests and static checks do not
replace real Harbor execution of the reference and the positive/negative controls.
