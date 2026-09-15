# Fresh solver trial — 2026-09-10

GPT-5.6 Sol, reasoning `high`, Codex 0.118.0, Harbor 0.22.0: **reward 1; 18/18 behavioral tests passed**. One fresh trial completed normally in 51m 49s, with no Harbor exceptions or retries. This is a single observed success, not an estimate of pass rate.

The solver started from the pinned clean Base plus the Codex executable. It received no reference solution, verifier files, or verifier feedback during the agent phase. The benchmark's executable files were unchanged. The agent could reach only the model relay; verification ran without network access. Gateway configuration and input hashes are in `run-plan.json`.

The model independently authored code, tests, and documentation across 42 files (986 insertions, 83 deletions). Its exact final edits are preserved in `submission.patch`, including new files. The submission was collected directly after the agent phase using a temporary Git index against Base; no curator repair was applied.

There were 331 captured model requests, all HTTP 200, including two successful native compactions. Harbor reported 39,868,730 input tokens (39,236,682 cached), 99,452 output tokens, and an estimated cost of $20.2119. Token totals include repeated context; the cost is Harbor's estimate, not a billing receipt. The solver encountered offline dependency-resolution and documentation/lint issues during its own checks and resolved them before completion.

## Evidence

- `summary.json`: score, lifecycle, test counts, token metrics, identities, and patch hash.
- `scored-trajectory.jsonl.gz`: complete Harbor trajectory joined with trial score and metadata.
- `remote-evidence.tar.gz`: raw Harbor results, verifier JSON/logs, native Codex session, submission, image audit, and run scripts; authentication files excluded.
- `submission.patch` and `diff-stat.txt`: exact final source changes.
- `model-last-message.md`: solver's own final response, distinct from independent verifier evidence.

Detailed readable trajectory and router captures are retained in `artifacts/dsh-migration-model-20260910/` at repository root. No benchmark or upstream PR was created.
