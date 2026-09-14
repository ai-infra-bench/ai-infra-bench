# Statement review — 2026-09-14

## Current: revision 4, agreed minimal interface

The user approved five minimal model tools with deterministic behavior tests.
The statement now specifies working-note replacement and complete text/record-ID
results, while leaving storage, optional fields and search ordering open. The
reference implementation and verifier have been revised together. Current
behavior mapping, source alignment and formal results are in `v2/`; the
previous mismatch described below is historical. No new solver pilot was run.

## Earlier: revision 3, user-workflow draft

The user requested a self-contained expansion of the desired capability, without
directing the solver to Codex. instruction.md now describes the actual workflow:
model-chosen note taking and reset, automatic continuation in one session,
selective original-evidence retrieval, normal restart, and local optional use.

This is a **contract revision**, not an equivalent shortening. The former six
tool names, extension entry path, JSON shapes, summary.md convention, exact
size/default/offset/cursor rules, literal search ordering/filter rules, and
specific path/error cases are no longer prescribed. The previous protocol draft
is preserved in instruction-protocol-draft.md. No protocol was moved into a
solver-visible appendix. Core goal/instruction retention is stated, but no
identical replay of every user message is specified.

The existing verifier still loads a fixed extension path, scripts six named
tools, expects summary.md, and checks exact protocol boundaries. It cannot fairly
grade arbitrary implementations of the new statement. README marks this mismatch
explicitly. Reviewing and aligning these assumptions is the next joint review;
tests have not been silently weakened or rerun. Earlier Oracle/live usage results
remain evidence for the earlier implementation and scenario, not the new draft's
solver performance. The full task is not currently claimed acceptance-ready.

Only statement/documentation/review metadata changed in this revision. The
implementation, environment, and verifier remain unchanged. Text diff and
artifact identities were checked; no behavioral test was needed for the edit.

## Earlier revisions

**Revision 2 supersedes the first rewrite below.** The user rejected the expanded
draft as too long. It is preserved in instruction-expanded-draft.md. Re-review
found repeated motivation, repeated session/workspace guarantees, and headings
that restated the tool workflow. The compact revision removes those repetitions
and groups each contract once, without moving requirements into another file.
The six tools' schemas, defaults, limits, error cases, transition timing,
retention, persistence, and exclusions remain explicit. The comparison examples
below have 511 and 487 whitespace-delimited words; the rejected draft had 894.
Current word count and hashes are recorded in statement-review.json. Test and
implementation files remain byte-identical; no model run or behavioral test was
repeated for this prose change. This review does not certify the entire task.

The following section records **revision 1**, whose layout is now superseded.

Scope: narrative rewrite of instruction.md, preserving the behavioral contract.
The user requested changing the statement first, then jointly reviewing traces
and tests. No implementation, verifier, environment, or model run was changed.

The statement now begins with the sustained-goal workflow and distinguishes the
working context from the persistent session. Requirements follow saving notes,
switching and continuing, retrieving evidence, and resuming. Tool result schemas
and pagination conventions are grouped after that workflow.

Comparison examples read: tasks/opencode-persistent-memory/instruction.md and
tasks/dsh-session-model-migration/instruction.md. These provided feature-request
writing examples, not evidence that this task has passed independent review.

## Semantic comparison

| Preserved contract | New location | Related existing scenarios |
| --- | --- | --- |
| Opt-in extension, fixed entry path, local API-key-compatible operation | Opening; Resume the same goal | ordinary; scripted local provider |
| Session-local exact-text notes, replacement, path/size errors, limits | Save working notes | notes, invalid |
| Entire tool batch completes once before switching; automatic continuation; no summary generation | Start a fresh context and continue | batch, rollover request sequence |
| System/user messages and latest summary survive; prior assistant/tool content leaves active context | Start a fresh context and continue | empty, rollover, repeated |
| Original message/tool text, stable scoped IDs, literal ordered search, filters, bounded previews | Retrieve original evidence | history, rollover, resume, isolation |
| Defaults, numeric bounds, Unicode units, opaque cursors, complete reconstruction, beyond-end behavior | Tool interface | notes, history, invalid |
| Restart persistence, session isolation, workspace preservation | Resume the same goal | resume, isolation; workspace checks |
| Documentation, implementation freedom, exclusions, work directory, existing typecheck caveat | Delivery and scope | Retained delivery requirements |

This is a mapping to existing tests, not a new completeness or fairness verdict.
Schema fields and numeric limits were compared with the old statement. No new
match-offset requirement or provider-specific strict-mode setting was added.
All user messages are still retained. Notes remain logical files, with storage
representation left to the solver. Pending design concerns were not resolved by
silently changing the contract.

## Version and evidence boundary

The full old statement is instruction-before-statement-review.md. The original
construction manifest is artifact-hashes-before-statement-review.json. Exact
old/new identities are in statement-review.json; artifact-hashes.json describes
the updated task files.

Prior construction results remain evidence about the unchanged implementation
and verifier against the former statement. The live model trials used the
reference implementation with their own scenario prompts; they did not evaluate
a solver reading either statement. No solver pilot or fresh behavioral run was
performed for this prose revision. Independent task review remains pending.

Validation: inspected the full text diff, compared contracts and existing
scenario assertions, and verified that every previously manifested file other
than instruction.md is byte-identical. No new tests were needed for this edit.
