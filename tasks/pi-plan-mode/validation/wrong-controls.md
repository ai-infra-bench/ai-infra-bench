# Wrong implementation controls

Each control is a complete patch that applies directly to pinned Base
`d981de1229ef899957bbe968bc8dcda02a21f477`. It includes the reference implementation
and one deliberate behavioral defect. Do not apply Oracle first. All ten controls
expect reward 0; the independent event-journal alternative remains a separate
Base-applicable correct implementation.

This format works with the ordinary CI case preparation path, which applies one
candidate patch to Base. The verifier observes behavior and never reads these
curator controls or compares a candidate with Oracle.

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
