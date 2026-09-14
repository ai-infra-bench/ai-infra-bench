# Pi context management v2 — review record

The task can be retained. The short user workflow and five minimal public tools
now define the contract; the former six-tool/file-pagination specification is
not the acceptance contract. Formal Harbor runs accepted both correct implementations
(11/11 each) and rejected Base plus all six incorrect controls. Every accepted
run completed without a Harbor exception. No solver-model pilot was run in this revision.

## Design and source alignment

The task implements model-requested context rollover in one persistent Pi
session. Its key Codex reference is `new_context_tool_skips_auto_compact_fallback`:
script a model tool call, inspect the subsequent real request, and verify that
normal tool execution continues without a summarization request. The local
history/notes implementation is inspired by Codex's public extension interface;
Codex's storage backend is not available in that source.

Keeping user requirements and carrying the latest working note are explicit Pi
requirements. Codex's referenced test actually removes its old user message.
Local API-key compatibility, restart persistence and session isolation are also
Pi requirements, not claims about undocumented Codex backend behavior.

The reference implementation records working-note updates and window boundaries
in Pi's session journal. A request only marks a pending transition; `turn_end`
installs the boundary after tool completion. The context hook rebuilds the next
input from retained instructions, the latest note, and current-window messages.
Original message entries remain searchable. Complete record reads and previews
around matches remove the old cursor/offset guessing workflow. This is a design
change validated with deterministic behavior, not a new real-model success claim.

## Semantic boundary and environment

Scripted model response -> real Pi provider adapter -> real tool execution ->
real session journal/context hook -> next HTTP model request. A normal process
exit/reopen exercises persistence. Only model generation and external evidence
production are scripted. The observer neither implements notes/history nor
rewrites candidate messages. Chat Completions and Responses both execute.

The pinned Pi Base and image remain unchanged. No Codex source, task-specific
fixtures, solution or verifier is added to the image. The final image is inspected
under the agent user with no network. Code runs directly from the edited source.
The task retains four CPUs, 8 GiB memory and a 36,000-second solver allowance.

## Contract and assertions

`coverage.json` maps the eleven scenarios to public behavior. Assertions inspect
actual outgoing requests, original text recovered by tools, normal process
restart, session identity and a workspace file. Tool names/required arguments
and text/ID fields are the user-approved public interface. Search ordering,
preview layout, acknowledgement fields, storage layout, fixed note paths,
8 KiB limits and the previous pagination conventions do not decide reward.

A separately stored JSON-note implementation passes the same behavior checks.
Its independence is supported by its write/read path: it atomically replaces a
session-specific file and does not recover notes from custom journal entries.
It also reverses search order and omits optional metadata. Thus its acceptance
checks more than patch similarity.

The new independent challenge clears notes, switches context and restarts. Old
conclusions must not reappear, while the original evidence remains readable.
A control that ignores empty writes isolates this requirement.

## Findings and repairs

- **P1, resolved contract mismatch:** the previous verifier required undisclosed
  file conventions, bounds and JSON pagination details after the statement was
  shortened. Replaced those checks with the five agreed interfaces and behavior.
- **Observer false rejection, resolved:** JSON serialization escaped multiline
  notes before comparison. The observer now traverses actual input strings.
- **Observer false rejection, resolved:** a new session's search can match its
  own search call. Isolation now reads returned records and checks for foreign
  content instead of demanding an empty result set.
- **Scoring boundary hardened:** the trusted parent runs separately from candidate
  Pi, which uses the image's agent UID and candidate-owned state directories.
  Candidate code cannot write the parent's reports. Early exit and an attempted
  reward-file overwrite are checked through Harbor, not just by exit status.
- **Formal collection failure, resolved in rerun:** an initial restrictive umask
  made reward.txt unreadable to the Harbor host. Reports now remain readable while
  only the trusted owner can write them. That interrupted run is retained and
  excluded from acceptance results.

## Evidence and limits

The old complete task is archived at
`artifacts/pi-context-hardening-20260914/task-before.tar.gz`; `before.json` records
its files, repository state and review-skill hashes. Initial probes and observer
failures are retained separately from `accepted-*` local results and the final
remote run. Runtime hashes bind formal evidence to the tested instruction,
configuration, solution, provider and scorer; later documentation updates are
identified separately.

This revision does not evaluate autonomous switching quality, real model
reliability, automatic token-budget policy, concurrent session writers or
cross-session long-term memory. Deterministic testing proves the execution
mechanism, not that a model will choose an effective search strategy. Prior live
model findings belong to the prior implementation/API. No commit or push was made.

## Subsequent directed live-model usage

A separate real-model usage pilot now accompanies the deterministic evidence.
See `live-model-review.md` and `live-model-results.json`. GPT-6 completed without
operator intervention; GPT-5.6 showed redundant resets and its second phase
completed after a documented operator interruption/recovery. The implementation
and deterministic verifier were unchanged. This supplies usability evidence,
not a reliability estimate or autonomous timing evaluation.

## Test update after live observations

Current verification has twelve scenarios and an additional history-loss control.
See `test-update-review.md` and `test-update-results.json` for the new formal matrix,
13 observer/watchdog unit tests, saved-trajectory replay, and one real-model smoke.
Earlier eleven-scenario results above remain historical evidence.
