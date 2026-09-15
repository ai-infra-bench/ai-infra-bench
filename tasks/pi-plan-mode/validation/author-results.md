# Author validation results

The strengthened verifier completed a fresh 13-case matrix through Harbor 0.23.0
on image `sha256:a68c346850d3b3ec045dd52aaf751e229e888ca365de99ab06a99fe88eeb0cda`.
Every case completed one trial with zero errored trials and the expected reward.
The standard repository case preparer applied every alternative/control patch
directly to pinned Base; no local preparer modification or Oracle layering was
needed.

| Case | Reward | Required behavior failures | Known original Base assertion observed |
| --- | ---: | --- | --- |
| `base` | 0 | C01, C02, C03, C04, C05, C06, C07, C08, C09, C10, C11, C12, C13, C14, C15, C16, C17, L01, L02, L03, L04 | Yes, exact pinned signature |
| `oracle` | 1 | None (18 contract + 4 lifecycle passed) | No |
| `alternative-event-journal` | 1 | None (18 contract + 4 lifecycle passed) | No |
| `accept-stale-revision` | 0 | C06, C15 | Yes, exact pinned signature |
| `accept-extension-control` | 0 | C07 | No |
| `replay-duplicate-approval` | 0 | C10, C16 | No |
| `allow-custom-planning-tools` | 0 | C02, C09, L01 | No |
| `replay-approved-resume` | 0 | L02 | No |
| `resume-original-toolset` | 0 | L01 | No |
| `drop-approved-request-context` | 0 | C10, C16 | No |
| `early-exit-zero` | 0 | C01, C02, C03, C04, C05, C06, C07, C08, C09, C10, C11, C12, C13, C14, C15, C16, C17, L01, L02, L03, L04 | No |
| `drop-done-progress` | 0 | C12 | Yes, exact pinned signature |
| `drop-ui-approved-request-context` | 0 | C16 | Yes, exact pinned signature |

Every run retained all 2,154 regression cases and the 50 original skips, with no
missing/extra cases or unaccepted regressions. Both correct implementations passed
2,104 regression cases with zero failures; neither used the conditional AuthStorage
allowance.

The new controls distinguish the intended omissions: disabling DONE handling
fails C12 while C10/C16 pass; omitting context only on UI Execute fails C16 while
C10/C12 pass. RPC behavior and the saved approved state alone cannot establish
that an interactive execution received the approved plan.

The early-exit control is rejected in two real paths: Vitest intercepts
`process.exit(0)` in contract workers; the independent lifecycle child exits
zero without the required state payload. Neither yields a passing reward.

The eight earlier controls produce the same source bytes as their former
Oracle-plus-delta composition. Regeneration and repeated-generation checks
confirmed Base applicability, TypeScript parsing, final file equality, and
stable patch/manifest/provenance bytes. See `wrong-control-provenance.json` and
`wrong-controls.md`. Formal outcomes and raw artifact hashes are in
`e2e-evidence.json`.

A separate observer probe exercised ordinary component-factory widgets,
subsequent requested renders, replacement and disposal. A correct reference
variant using only a component-factory widget for /todos passed the real SDK
C12/C16 checks, as did the snapshot and event-journal implementations. The
observer uses public TUI components and the actual Theme; only the physical
terminal is replaced with an in-memory output sink. Displayed custom transcript
messages are also rendered through pi's public message component and registered
renderer; hidden messages do not count as visible plan text.

The six scoring-integrity self-tests passed. The intentionally strict earlier
matrix remains historical evidence in `initial-matrix-evidence.json`; its results
do not certify the revised verifier. Original Base AuthStorage reproduction and
the exact regression policy remain in `baseline-environment.md`.

`candidate-rechecks.json` records fresh grading of four retained coding-agent
implementations. These are regrades of existing source archives, with restored
file hashes checked before verification, not new model attempts on the clarified
prompt. No success-rate or ranking claim follows from them.

Local task validation and public image delivery are separate. The immutable
local image is retained; publication still requires the repository workflow to
validate and publish the actual registry image.

A final standalone Harbor Oracle run on the final task configuration also
returned reward 1 with zero errored trials. Its completed checks, input hashes
and raw artifact hashes are recorded in `e2e-evidence.json`.
