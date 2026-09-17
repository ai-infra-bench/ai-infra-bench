# Wrong implementation controls

Each negative control is a complete patch that applies directly to pinned Base
`d981de1229ef899957bbe968bc8dcda02a21f477`. It includes the reference implementation
and one deliberate behavioral defect. Do not apply Oracle first. All ten negative
controls expect reward 0. The two positive controls below also apply directly to
Base and expect reward 1; their formal outcomes are recorded in `e2e-evidence.json`.

This format works with the ordinary CI case preparation path, which applies one
candidate patch to Base. The verifier observes behavior and never reads these
curator controls or compares a candidate with Oracle.

## Positive controls

| Control | Permitted difference | Purpose |
| --- | --- | --- |
| `alternative-event-journal` | Independent event-journal implementation of the same plan lifecycle | Checks that the verifier accepts a materially different state/persistence implementation |
| `minimal-public-state` | Omits public `approvedRevision`, adds changing diagnostic metadata, returns submitted state only in result details with ordinary acknowledgement text, and supplies rejection reasons without the fixed error-code field | Checks the revised public-output contract: compare the five required state fields, allow extra fields, accept one structured submission channel and avoid fixed error-code vocabulary |

`minimal-public-state` is derived from the reference implementation and changes
its public representation. It is not an independent algorithm and does not
replace `alternative-event-journal` as that check. It keeps the same identity,
revision, tool restrictions, approval execution and normal-resume obligations.
Its volatile diagnostic field must not break idempotence or resume comparisons.

The current verifier does not require a particular revision origin or increment
size: accepted submissions must strictly increase the revision. Normal-state
identity/revision sentinels and unknown-operation sentinels are also not fixed.
These are contract freedoms; the representation control above is not claimed to
exercise every possible choice.

## Negative controls

| Control | Deliberate defect | Intended observation |
| --- | --- | --- |
| `accept-stale-revision` | Accepts any nonnegative revision instead of the current submitted revision | C06 rejects old and future revisions; C15 rejects a stale UI selection |
| `accept-extension-control` | Removes the input-source boundary | C07 rejects extension-origin controls |
| `replay-duplicate-approval` | Removes approved-version idempotence | C10 observes a second request or duplicate approval message |
| `allow-custom-planning-tools` | Retains arbitrary original custom tools during planning | C02/C09 observe the wrong tool set and actual custom-tool side effects; L01 checks resume |
| `replay-approved-resume` | Re-dispatches an approved snapshot while restoring a session | L02 observes requests or duplicate approval messages on reopen |
| `resume-original-toolset` | Advertises original tools on planning resume instead of the restricted subset | L01 observes the wrong restored tool selection; the regular dispatch guard remains |
| `drop-approved-request-context` | Saves the correct snapshot but filters it out of provider input | C10/C16 inspect the actual execution request, independently of persisted messages |
| `early-exit-zero` | Exits successfully as soon as the extension factory runs | Exact test inventories and independent child output reject early termination |
| `drop-done-progress` | Omits the completed-turn handler that consumes `[DONE:n]` | C12 observes that `/todos` never advances while the approved snapshot stays unchanged |
| `drop-ui-approved-request-context` | Omits the approved snapshot from provider input only after UI Execute | C16 rejects missing execution context; RPC approval, persisted state, message count, tools, and the scripted write still work |

The request-context controls matter because a scripted provider performs its next
tool call even if plan text is missing. Stored `plan-approved` messages and file
side effects alone cannot establish what the model actually received. The UI-only
control distinguishes the interactive path from otherwise correct RPC behavior.

Rejection reasons are not graded against an enum or a phrase. The verifier's
`hasReason` helper finds a nonblank string in extra result metadata, recursively;
it does not judge arbitrary natural-language meaning. Negative controls remain
distinguishable through real state transitions, provider requests, tool
selection, filesystem effects, UI races and independent-process resume. All
18 contract and 4 lifecycle cases remain required.

Regenerate from the retained image, without network access:

```bash
python3 tasks/pi-plan-mode/validation/generate_wrong_controls.py --image ai-infra-bench/pi-plan-mode:base-d981de1229ef
```

Alternatively, pass `--base-dir /path/to/pi-checkout` containing the pinned Base
commit. The generator reads Base from Git objects, applies `solution/oracle.patch`
in a disposable directory, then creates each complete patch. It checks unique
mutation anchors, Base applicability, and equality of the resulting file bytes
before writing output. It also checks TypeScript parsing when a supported Node
executable is available; `--node` can select that executable. It preserves manifest entries outside
its ten managed controls. It never edits the input checkout or runs a control.

The eight original controls retain the exact source produced by their former
Oracle-plus-delta composition. Changing their packaging does not change their
intended defects. `wrong-control-provenance.json` records generation checks; formal
runtime outcomes are recorded separately in `e2e-evidence.json`. Static checks do
not establish that a control reached its intended path or received the right reward.
The 2026-09-17 formal matrix validated Base, Oracle, both positive controls
and all ten negative controls against the revised statement and verifier. Four
saved-candidate replays also completed; see `candidate-rechecks.json`. Earlier
outcomes remain evidence only for the snapshots on which they ran.
