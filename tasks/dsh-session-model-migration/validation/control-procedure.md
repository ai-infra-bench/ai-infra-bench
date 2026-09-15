# Reproduce controls

The nine patch controls in `ci-cases.json` are full patches against Base. Apply the named patch through an Oracle solution and run the normal Harbor task with the separate verifier. Base uses `nop`; the reference uses `solution/solve.sh`. Retain the task configuration and both image identities from `e2e-evidence.json`.

The extra `forged-runner` case uses an Oracle solution that runs the following in the agent container, with `validation/forged-runner.mjs` copied to `/solution/forged-runner.mjs` by the curator:

```bash
set -euo pipefail
cd /workspace/deepseek-harness
cp /solution/forged-runner.mjs node_modules/vitest/vitest.mjs
echo FORGED_RUNNER_INSTALLED_IN_AGENT
git diff --exit-code
```

Run the normal artifact collection and separate verifier afterward. The agent source patch must be empty, the marker must be present in `agent/oracle.txt`, the verifier must execute Base's actual 22 tests, and reward must be 0. Full commands, trial IDs, transferred artifacts, and reports are in the raw evidence archive. This control is outside the patch-only CI manifest because it intentionally mutates agent-side dependencies.
