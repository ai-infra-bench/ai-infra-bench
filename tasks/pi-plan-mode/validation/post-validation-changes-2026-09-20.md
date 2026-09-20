# Changes after the recorded validation, 2026-09-20

The evidence in this directory (`e2e-evidence.json` and the files it hashes) was recorded by the task author before the edits below. It has **not** been regenerated: `audit_task_artifacts.py` reports the affected hashes as stale, which is accurate. The full case matrix has to be rerun on linux/amd64 (CI does this natively) before the evidence is refreshed.

Made by Andyyesiyu's session while unifying the pi task PRs onto `agent/base`; reasons and details are in the commit "pi-plan-mode, pi-safe-file-rollback: reproducible build, platform-independent grading directory, explicit platform error".

| File | Change | Why |
|---|---|---|
| `environment/build/Dockerfile.template`, `environment/Dockerfile` | model catalog from the sha256-pinned `@earendil-works/pi-ai` 0.85.1 package, `RUN --network=none npm run build:offline` | `npm run build` refetches the catalog from live APIs and stopped compiling on 2026-09-19 (`kimi-coding` dropped upstream); the image could not be built from scratch any more |
| `tests/test.sh` | reports and reward are produced in a container-local root-owned `$PI_GRADER_OUT` and published to `/logs/verifier` in an EXIT trap | `/logs` is a host bind mount; on macOS it does not enforce ownership, uid 65534 could overwrite `reward.txt`, and C00 failed for the Oracle |
| `tests/plan.contract.test.ts` | C00 probes `$PI_GRADER_OUT/reward.txt` | follows the line above |

Re-checked locally (linux/arm64 image built from the new Dockerfile, Harbor 0.22.0 through `tools/local_task_validation.py`, macOS host): Base 0, Oracle 1 (Oracle was 0 on this host before the grading-directory change, 17/18 with only C00 failing). One grok-4.6 rollout on the changed task: reward 0 at the scope check (`changed_frozen_files: packages/coding-agent/test/plan-mode-utils.test.ts`, the agent appended new `describe` blocks to that file); replayed without that edit it scores contract 16/18 (C15, C16), lifecycle 3/4 (L04), P2P pass. The instruction's "relevant tests ... You may update `plan-mode-extension.test.ts` and add coding-agent tests" does not say whether other existing test files may grow; worth stating explicitly.

Not rerun: the 12 control cases and the saved-answer regrades.
