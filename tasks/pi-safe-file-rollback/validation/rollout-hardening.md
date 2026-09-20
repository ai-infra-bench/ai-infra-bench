# Rollout-driven verifier hardening, version 0.0.4

This release corrects three verifier boundaries exposed during completed-answer
review. The instruction, pinned Base, retained image, Oracle and earlier controls
are unchanged. No new model inference was performed. See the
[structured record](rollout-hardening.json) for hashes and preserved anomalies.

## Changes and contract

- The third legacy TUI fixture, `interactive-mode-startup-input.test.ts`, now
  supplies the required public disabled/ready API. Original assertions and all
  2,158 regression identities, including 50 skips, remain unchanged.
- The SDK peer calls documented `AgentSessionRuntime.fork`, rather than the
  nonexistent `AgentSession.fork`. A ready fork succeeds and produces the expected
  conversation boundary. Interrupted/blocked gates exercise that same runtime,
  observe its actual session even when an operation throws, and check session,
  effective messages, fixture files and provider requests. Public cancellation
  results are accepted; state need only remain enabled and unresolved. Navigation
  checks use a changed target because same-leaf navigation is a documented no-op.
- Filesystem failure injection keeps Git repository ownership stable while
  denying in-place writes and rename replacement. A complete preflight refusal
  is allowed; a pending restore must remain inspectable, gated and retryable.

## Accepted validation

The final frozen inputs completed 13 author Harbor trials: Base 0; Oracle,
independent blob-journal implementation and minimal-metadata variant 1; all nine
negative controls 0. All 13 original launcher checks matched and all trials
completed without Harbor errors. Inputs and prepared cases match their pre-run
hashes. The new missing-runtime-fork-gate control builds and passes all 2,108
active regressions (plus 50 skips) and stable auth. It passes ready fork but fails
exactly five recovery-fork cases, earning 0 with 21/26 behaviors.

Oracle, alternative and metadata variant all reached a real blocked filesystem
restore, remained blocked after restart, and succeeded after access was restored.
The test still permits a correct earlier refusal. An isolated public-cancellation
variant passes three real boundary cases and emits four `cancelled: true` replies.
It is a targeted diagnostic, not another full-solution reward.

The third mock's unchanged three tests pass. Dropping only the production
startup queue push makes exactly the original `early prompt` queue assertion
fail (2/3 pass). The same fixture bytes and all 680 delivered production source
files match after restoring the mutation. Historical two-fixture sensitivity
controls are retained separately in [regression-fixtures.json](regression-fixtures.json).

## Complete saved-answer replays and orchestration anomaly

All four complete source archives were restored and checked before actual Harbor
scoring, and archive/prepared input hashes remain unchanged. Observed rewards
are TraeX 0, Astra xhigh 1, Sol medium 0, Sol xhigh 0, with 2/26, 26/26, 19/26 and
25/26 behaviors respectively. The 2,158-case original inventory, including 50
skips, is retained. Astra has only the already accepted Base AuthStorage timestamp
signature, and its independent stable counterpart passes.

Three of four original saved-answer launcher checks matched. The launcher
mistakenly entered expected reward 1 for Sol xhigh, although prior completed
review and the fixture-only replay already established reward 0. Its original
check exit 2, expected value, summary and logs are preserved. A separate read-only
check of the unchanged Harbor result against expected 0 passes; no grading rerun
or candidate change was made. Thus this record does not claim 17/17 original
machine expectation checks matched.

Sol xhigh still fails the same directory-to-file `ENOTDIR` snapshot case, while
its TUI regression now passes. TraeX's new ready-fork case stops at its already
known first-prompt recovery guard; it is not evidence of an independent fork bug.
Sol medium was 19/25 under v0.0.2 and is 19/26 here: ready fork passes, while the
conflict-resolution retry added in v0.0.3 exposes its existing whole-snapshot
conflict policy on an unrelated human file. This release did not change that case.

## Evidence boundaries

Three early draft matrix launches were stopped before completion while review
removed overstrict state equality, admitted public cancellation, and excluded
same-leaf no-op navigation. Their inputs, interruption hashes and raw partial
logs remain separate with `accepted_evidence: false`; none count as completed
qualification. Final author and saved-answer results all use the same unchanged
runtime verifier. Documentation and final delivery manifests were refreshed only
after execution. Machine-specific paths and raw logs remain outside the task.

[e2e-evidence.json](e2e-evidence.json) binds the author matrix;
[saved-answer-regrade.json](saved-answer-regrade.json) binds full source replays
and their original checks; [public-cancellation-diagnostic.json](public-cancellation-diagnostic.json)
and the regression fixture record bind the targeted controls. These results do
not establish model solve rates or exhaustive correctness beyond the tested scope.

The task-local `.gitattributes` disables outer whitespace warnings for `*.patch`
data files. Unified-diff context prefixes and context tabs are valid patch bytes;
the 12 actual patches remain checked with `git apply --check`. This delivery
metadata correction does not change the frozen verifier, controls or scores.
