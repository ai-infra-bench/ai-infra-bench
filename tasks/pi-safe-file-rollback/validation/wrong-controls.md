# Negative controls

Each control is a complete patch against Base `d981de1229ef899957bbe968bc8dcda02a21f477`, including the production implementation except for the deliberate defect below. They do not require applying Oracle first. Base and Oracle are the CI runner's built-in cases; `ci-cases.json` lists these controls and the separately maintained positive alternative.

| Case | Deliberate defect | Expected distinguishing behavior |
| --- | --- | --- |
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

Keeping internal records of abandoned branches is permitted when they are not
eligible public targets and cannot contaminate later behavior. The branch control
therefore includes the externally observable eligibility defect; private storage
retention alone is not treated as incorrect.
