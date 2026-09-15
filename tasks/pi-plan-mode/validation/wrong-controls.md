# Wrong implementation controls

These controls apply **after Oracle** and each changes one behavior in the Plan Mode extension. All expect reward 0. The generated provenance records patch application and Node syntax checks only; runtime failures must be confirmed through the task's actual verifier before publishing evidence.

| Control | Deliberate defect | Intended observation |
| --- | --- | --- |
| `accept-stale-revision` | Accepts any nonnegative revision instead of the current submitted revision | C06 rejects old and future approval revisions |
| `accept-extension-control` | Removes the input-source boundary | C07 rejects extension-origin controls |
| `replay-duplicate-approval` | Removes approved-version idempotence | C10 observes a second request or duplicate approval message |
| `allow-custom-planning-tools` | Retains arbitrary original custom tools during planning | C02/C09 observe the wrong tool set and real custom-tool side effects |
| `replay-approved-resume` | Re-dispatches an approved snapshot while restoring a session | L02 observes requests or duplicate approval messages on reopen |
| `resume-original-toolset` | Advertises original tools on planning resume instead of the restricted subset | L01 observes the wrong restored tool selection; the regular dispatch guard remains |
| `drop-approved-request-context` | Saves the correct snapshot but filters it out of provider input | C10/C16 must inspect the actual execution request, not just the persisted message |
| `early-exit-zero` | Exits successfully as soon as the extension factory runs | Exact test inventories and independent child output must reject early termination |

Regenerate after any Oracle source correction:

```bash
python3 tasks/pi-plan-mode/validation/generate_wrong_controls.py \
  --oracle-dir /path/to/pi-oracle
```

The generator reads the Oracle worktree, uses unique source anchors, checks each patch with `git apply --check`, checks mutated TypeScript with `node --check`, and updates patch SHA-256 entries in `ci-cases.json`. It never edits the Oracle. Existing manifest entries outside its eight managed names, including a subsequently completed correct alternative, are preserved.

The request-context control is important: a scripted provider will perform its next tool call even if the plan text is missing. Checking the stored `plan-approved` message and the resulting file alone would not detect that failure.
