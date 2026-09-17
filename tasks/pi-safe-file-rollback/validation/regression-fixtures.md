# Regression fixture compatibility

Introduced in version 0.0.2, the verifier supplies the task-specified disabled-session API to two legacy TUI
regression fixtures after loading them from the pinned Base. It preserves every
original assertion, event sequence, deferred barrier and testcase identity.

`5943-session-start-notify.test.ts` calls the private rebind method on three
partial receiver objects without a session. The startup/replacement test in
`startup-session-rebind-duplicate-subscription.test.ts` uses two empty objects
only to distinguish session identity. Neither fixture originally supplied
`getRollbackState()`, which the public task now requires on real sessions.

The adaptation gives these five mock objects the public disabled response:
`{ enabled: false, status: "ready" }`. The two identity objects remain distinct.
Pinned source-anchor counts guard the adaptation. No assertion, production code,
test selection, failure tolerance or reward condition is changed. This is a
fixture correction, not an exemption for failed tests.

A saved Codex / GPT-6 Astra xhigh answer exposed this issue: its 25 behavior cases
passed but four legacy regressions failed on the incomplete receivers. Keeping
that answer unchanged and supplying the mock API made all eight tests in the
two files pass. A complete diagnostic Harbor replay then passed all 25 behavior
cases and the full original 2,158-case regression inventory, earning reward 1.
The historical reward 0 remains a record of the old verifier.

The declared original regression inventory remains 2,158 cases, including the
same 50 existing skips. Enabled recovery behavior is still exercised separately
through the real SDK, RPC and terminal; these disabled-state stubs do not replace
those checks. Current validation records the formal author-control matrix
and the unchanged saved-answer replay in [e2e-evidence.json](e2e-evidence.json)
and [saved-answer-regrade.json](saved-answer-regrade.json).

An independent review executed the formal fixture preparation, confirming that
only these two files changed and that removing the added public API restores the
exact Base bytes. It also ran the eight original tests against targeted negative
controls, retaining all original assertions:

| Input | Passed / total | Observed result |
| --- | --- | --- |
| Unchanged saved answer with corrected fixtures | 8/8 | Pass |
| Extension binding moved before render/subscription | 4/8 | Existing ordering, message and subscription assertions fail |
| Stale-session identity guard removed | 7/8 | Existing subscription-count assertion fails |

These checks demonstrate continued detection of the original TUI regressions.
Hashes and results are recorded in [regression-fixtures.json](regression-fixtures.json).
