# Negative controls

Each control is a complete patch against Base `d981de1229ef899957bbe968bc8dcda02a21f477`, including the production implementation except for the deliberate defect below. They do not require applying Oracle first. Base and Oracle are the CI runner's built-in cases; `ci-cases.json` lists these controls and the separately maintained positive controls described in [alternative-correctness.md](alternative-correctness.md).

| Case | Deliberate defect | Expected distinguishing behavior |
| --- | --- | --- |
| `missing-runtime-fork-gate` | Removes only the real runtime fork readiness guard. | Interrupted recovery must prevent session replacement through the public fork API, after ready-state fork is proven operational. |
| `memory-only` | Journal publication is disabled. | A restarted session must retain enablement and checkpoints. |
| `checkpoint-at-request-end` | The new request is published only after it finishes. | Killing the first or a later request must retain its pre-request checkpoint and require recovery. |
| `files-only` | Conversation restoration is omitted. | Removed messages must disappear from effective provider context and remain absent after restart. |
| `conversation-only` | Restore applies no file images. | Workspace bytes, existence, and permissions must return to the selected boundary. |
| `ignore-conflicts` | Idle-edit conflicts are discarded. | Conflicts, including edits between requests, must reject the entire rollback without mutation. |
| `skip-startup-recovery` | Startup discards unresolved execution/restore state. | Interrupted sessions remain gated; unfinished restores must resume before execution. |
| `abandoned-branch-included` | Abandoned descendants are exposed as eligible public targets without ancestry validation. | Only current ancestors may be listed or restored. |
| `early-process-exit-zero` | Enabled safe-rollback SDK construction exits with code zero; disabled sessions behave normally. | Successful process exit without serving the requested behavior earns no credit. |

Regenerate with `python3 validation/generate_controls.py --base-repo /path/to/pi`. The script reads the pinned Base object and current `solution/oracle.patch`, works in temporary directories, checks clean Base application, and verifies complete resulting file contents against each intended mutation before publishing patches. It preserves unrelated CI cases, including the alternative. Patch hashes and generation checks are recorded in `control-generation.json` and `ci-cases.json`.

Compilation and behavioral rewards are separate checks. These controls must compile; a build failure is not evidence that the intended semantic defect was detected. Recorded matrix evidence is the authority for observed rewards.

Version `0.0.3` retains all eight negative controls and all 25 behavioral scenarios.
The first-person statement removes unnecessary metadata, list-order,
acknowledgement-payload and preflight-status requirements. The verifier replaces
those constraints with direct conversation restoration and conflict-resolution
retry checks; crash recovery, manual-edit protection, branch isolation and
execution gating remain required. The added `minimal-checkpoint-metadata`
positive is derived from Oracle to challenge representation bias, not to replace
any negative control or provide another independent recovery algorithm.

The current author matrix comprises Base, Oracle, two positive controls and
these nine negative controls. Expected outcomes are not recorded outcomes:
consult the current [e2e-evidence.json](e2e-evidence.json) for completed trials
bound to the current verifier. Individual negative controls may fail different
numbers of cases after behavioral checks are strengthened; the relevant evidence
is that their intended defects are observed and they earn zero reward.

Keeping internal records of abandoned branches is permitted when they are not
eligible public targets and cannot contaminate later behavior. The branch control
therefore includes the externally observable eligibility defect; private storage
retention alone is not treated as incorrect.

Version `0.0.4` adds `missing-runtime-fork-gate`, bringing the canonical author
inventory to 13 (Base, Oracle, two correct controls, nine negative controls).
Its full patch differs from Oracle only by the deleted runtime fork guard.
The third TUI fixture's bad startup-queue mutation and the public cancellation
variant are separate diagnostic controls; they do not increase this inventory.
`generate_controls.py --cases missing-runtime-fork-gate` can regenerate only the
new patch while preserving earlier control provenance.
