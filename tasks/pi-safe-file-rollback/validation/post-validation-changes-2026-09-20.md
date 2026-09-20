# Changes after the recorded validation, 2026-09-20

The evidence in this directory (`e2e-evidence.json` and the files it hashes) was recorded by the task author before the edits below. It has **not** been regenerated: `audit_task_artifacts.py` reports the affected hashes as stale, which is accurate. The full case matrix has to be rerun on linux/amd64 (CI does this natively) before the evidence is refreshed.

Made by Andyyesiyu's session while unifying the pi task PRs onto `agent/base`; reasons and details are in the commit "pi-plan-mode, pi-safe-file-rollback: reproducible build, platform-independent grading directory, explicit platform error".

| File | Change | Why |
|---|---|---|
| `tests/run_verifier.py` | `prepare()` stops with `Unsupported verifier platform <os>/<machine>: this task verifies on linux/amd64 only` when not on linux/amd64 | on an arm64 host the verifier reported `Installed dependencies were modified` (the pinned `dependencies_sha256` covers the amd64 `node_modules`), which reads as candidate tampering; the ptrace supervisor is amd64-specific as well |
| `README.md` | platform paragraph | states the requirement |

On linux/amd64 the added check is a no-op, so verdicts there are unchanged. Re-checked locally only that the new message appears on linux/aarch64 (Base 0, Oracle 0 with that error). Nothing else could be rerun on the arm64 host; no case was rerun on linux/amd64.
