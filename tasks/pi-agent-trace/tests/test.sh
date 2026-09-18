#!/usr/bin/env bash
# Verifier entrypoint. Copies verifier-owned tests into the workspace test tree
# so vitest resolves workspace aliases, then requires every inventoried case to
# complete. A successful process exit is never sufficient on its own.
#
# Trust boundary: the agent phase already runs as the unprivileged `node` user
# (task.toml [agent].user), but this script runs as root. Every step that
# executes candidate code -- the whole pi suite in PASS_TO_PASS (which runs the
# candidate's new test file), the contract suite (which imports the candidate
# extension) and the lifecycle suite (which spawns child pi with it) -- is run
# as `node` via `su`, so candidate code can never rewrite the root-owned test
# runner, interpreter or baseline that the scoring depends on, and never writes
# the reward file. Reports are produced by `node` into a node-owned scratch dir;
# root parses them and writes the reward. `node` processes are reaped between
# steps so nothing candidate-spawned can rewrite a report or the reward after
# the fact. (A candidate can still, in principle, tamper with the report of the
# suite it runs inside from within that same process; that is candidate-side
# cheating for the hack screen, not a runner/scorer substitution.)
set -uo pipefail
mkdir -p /logs/verifier
rm -f /logs/verifier/{reward.txt,reward.json,contract-junit.xml,lifecycle-junit.xml,contract-summary.json,lifecycle-summary.json,scope.log}
export PI_WORKSPACE=/workspace/pi
export PI_VERIFIER_FIXTURES=/tests/fixtures
export PI_OFFLINE=1 PI_TELEMETRY=0 PI_NO_LOCAL_LLM=1
# Verification never contacts a real model. The image is no-network, but make it
# impossible anyway: drop every credential pi's env-api-keys.ts or pi-test.sh
# knows about, so key-gated suites stay skipped and no provider is configured.
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_OAUTH_TOKEN OPENAI_API_KEY GEMINI_API_KEY \
  GOOGLE_CLOUD_API_KEY GROQ_API_KEY CEREBRAS_API_KEY XAI_API_KEY OPENROUTER_API_KEY ZAI_API_KEY \
  ZAI_CODING_CN_API_KEY MISTRAL_API_KEY MINIMAX_API_KEY MINIMAX_CN_API_KEY AI_GATEWAY_API_KEY \
  OPENCODE_API_KEY COPILOT_GITHUB_TOKEN GH_TOKEN GITHUB_TOKEN HF_TOKEN DEEPSEEK_API_KEY \
  FIREWORKS_API_KEY KIMI_API_KEY MOONSHOT_API_KEY NVIDIA_API_KEY TOGETHER_API_KEY BASETEN_API_KEY \
  CLOUDFLARE_API_KEY RADIUS_API_KEY ANT_LING_API_KEY XIAOMI_API_KEY XIAOMI_TOKEN_PLAN_AMS_API_KEY \
  XIAOMI_TOKEN_PLAN_CN_API_KEY XIAOMI_TOKEN_PLAN_SGP_API_KEY QWEN_TOKEN_PLAN_API_KEY \
  QWEN_TOKEN_PLAN_CN_API_KEY AZURE_OPENAI_API_KEY AZURE_OPENAI_BASE_URL AZURE_OPENAI_RESOURCE_NAME \
  GOOGLE_APPLICATION_CREDENTIALS GOOGLE_CLOUD_PROJECT GCLOUD_PROJECT GOOGLE_CLOUD_LOCATION \
  AWS_PROFILE AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_REGION \
  AWS_DEFAULT_REGION AWS_BEARER_TOKEN_BEDROCK AWS_CONTAINER_CREDENTIALS_RELATIVE_URI \
  AWS_CONTAINER_CREDENTIALS_FULL_URI AWS_WEB_IDENTITY_TOKEN_FILE
# HOME must be writable by the `node` user that runs the suites (su -p keeps it).
export HOME=/tmp/pi-verifier-home
rm -rf "$HOME" && mkdir -p "$HOME" && chown node:node "$HOME"
# Node-owned scratch for the reports the suites produce; /logs/verifier stays
# root-only so the reward file is never candidate-writable.
VOUT=/tmp/pi-verifier-out
rm -rf "$VOUT" && mkdir -p "$VOUT" && chown node:node "$VOUT"

# Run a command as the unprivileged node user, preserving the verifier env
# (-p keeps HOME/PI_*/NODE_OPTIONS and the unset provider keys). exec so the
# timeout/kill lands on node, not on su.
as_node() { su -p node -s /bin/bash -c "cd /workspace/pi/packages/coding-agent && $*"; }
# Kill anything the candidate left running before root reads a report or writes
# the reward, so no node-owned process can rewrite them afterwards.
reap_node() {
  pkill -9 -u node 2>/dev/null || true
  for _ in $(seq 1 100); do pgrep -u node >/dev/null 2>&1 || break; sleep 0.1; done
}

if ! cd /workspace/pi/packages/coding-agent; then
  echo "verifier: workspace /workspace/pi/packages/coding-agent is missing" | tee /logs/verifier/verifier-error.log
  printf '0\n' > /logs/verifier/reward.txt
  printf '{"reward":0,"command_exit_code":1,"error":"workspace missing"}\n' > /logs/verifier/reward.json
  exit 0
fi
as_node 'rm -rf test/__verifier__' || true

contract_rc=0
contract_integrity_rc=0
lifecycle_rc=0
lifecycle_integrity_rc=0
p2p_rc=0
p2p_check_rc=0

# Every root git call below reads a throwaway copy of the index (GIT_INDEX_FILE),
# so `git status`/`git add -N` can refresh their stat cache without ever
# rewriting the real node-owned .git/index -- a root-owned index would break git
# for the node suites. GIT_INDEX_FILE is inline on each call, never exported, so
# it does not leak into the `su node` suites (pi's own tests use the real index).
SNAP_INDEX=/tmp/pi-snap-index
cp /workspace/pi/.git/index "$SNAP_INDEX" 2>/dev/null || true
G="GIT_INDEX_FILE=$SNAP_INDEX git -C /workspace/pi"

# Snapshot of what the agent changed, for review of real rollouts (never affects reward).
{
  eval "$G status --short --untracked-files=all"
  echo "--- diff vs Base (tracked + untracked, excluding node_modules/dist) ---"
  eval "$G add -N --all -- . ':!**/node_modules/**' ':!**/dist/**'" 2>/dev/null || true
  eval "$G diff d981de1229ef899957bbe968bc8dcda02a21f477 -- . ':!**/node_modules/**' ':!**/dist/**'" 2>/dev/null | head -c 4000000
} > /logs/verifier/agent-changes.patch 2>&1 || true
# The snapshot's `add -N` recorded intent-to-add for untracked files in this index
# copy; refresh it to a clean copy of the real index so the scope and PASS_TO_PASS
# checks below see new files as untracked (allowed) and flag only real edits.
cp /workspace/pi/.git/index "$SNAP_INDEX" 2>/dev/null || true


# Toolchain and core scope: the instruction keeps the work inside the extension directory,
# a new unit test file and documentation, and forbids changes to pi core. The verifier
# rejects a submission that changed pi source or the build/test toolchain it is about to
# execute (configs, manifests, scripts), whether by editing a tracked file or adding one.
# Scratch files elsewhere are not penalised.
scope_rc=0
scope_changes="$(eval "$G status --porcelain --untracked-files=all -- . ':!**/node_modules/**' ':!**/dist/**'" 2>/dev/null | awk '{print $NF}' \
  | grep -E '^(packages/[^/]+/src/|scripts/|\.github/|\.npmrc$|package\.json$|package-lock\.json$|tsconfig[^/]*\.json$|biome\.json$|vitest[^/]*$|vite\.config[^/]*$|packages/[^/]+/(package\.json|tsconfig[^/]*\.json|vitest[^/]*|vite\.config[^/]*)$)' || true)"
if [ -n "$scope_changes" ]; then
  {
    echo "SCOPE: the submission changed pi core or the build/test toolchain, which the instruction forbids:"
    echo "$scope_changes"
  } | tee /logs/verifier/scope.log
  scope_rc=1
fi
# Never execute vite's transient config bundles left by the agent phase. The
# dirs live under root-owned node_modules, so node cannot recreate them; clear
# the contents and hand the empty dirs back to node for fresh temp bundles.
for d in /workspace/pi/node_modules/.vite-temp /workspace/pi/node_modules/.vite \
         /workspace/pi/packages/*/node_modules/.vite-temp /workspace/pi/packages/*/node_modules/.vite; do
  rm -rf "$d" 2>/dev/null || true
  mkdir -p "$d" 2>/dev/null && chown node:node "$d" 2>/dev/null || true
done

# PASS_TO_PASS: pi's own coding-agent suite must match the Base baseline recorded
# in the image, and existing test files must be untouched (new files are fine).
if ! eval "$G diff --quiet d981de1229ef899957bbe968bc8dcda02a21f477 -- packages/coding-agent/test"; then
  echo "PASS_TO_PASS: existing test files were modified" | tee /logs/verifier/pass-to-pass.log
  eval "$G diff --name-only d981de1229ef899957bbe968bc8dcda02a21f477 -- packages/coding-agent/test" | tee -a /logs/verifier/pass-to-pass.log
  p2p_check_rc=1
else
  as_node "exec timeout 900 node ../../node_modules/vitest/vitest.mjs run --retry 2 --maxWorkers=4 --reporter=junit --outputFile=$VOUT/pass-to-pass-junit.xml" \
    > /logs/verifier/pass-to-pass.log 2>&1 || p2p_rc=$?
  reap_node
  cp "$VOUT/pass-to-pass-junit.xml" /logs/verifier/pass-to-pass-junit.xml 2>/dev/null || true
  tail -n 20 /logs/verifier/pass-to-pass.log
  # The baseline lives in the agent-writable image; check_pass_to_pass.py verifies it
  # against pins (Base case inventory, key-gated skipped set, failure cap) that hold
  # across image builds and platforms, so a rewritten baseline is rejected.
  python3 /tests/check_pass_to_pass.py /opt/pi-baseline/coding-agent-junit.xml /logs/verifier/pass-to-pass-junit.xml /tests/baseline-pins.json || p2p_check_rc=$?
fi

as_node 'mkdir -p test/__verifier__' || true
cp /tests/at_support.ts /tests/at.contract.test.ts /tests/at.lifecycle.test.ts test/__verifier__/

as_node "NODE_OPTIONS=--expose-gc exec timeout 900 node ../../node_modules/vitest/vitest.mjs run --reporter=junit --outputFile=$VOUT/contract-junit.xml test/__verifier__/at.contract.test.ts" \
  > /logs/verifier/contract.log 2>&1 || contract_rc=$?
reap_node
cp "$VOUT/contract-junit.xml" /logs/verifier/contract-junit.xml 2>/dev/null || true
cat /logs/verifier/contract.log
python3 /tests/check_junit.py /logs/verifier/contract-junit.xml contract || contract_integrity_rc=$?

as_node "exec timeout 600 node ../../node_modules/vitest/vitest.mjs run --reporter=junit --outputFile=$VOUT/lifecycle-junit.xml test/__verifier__/at.lifecycle.test.ts" \
  > /logs/verifier/lifecycle.log 2>&1 || lifecycle_rc=$?
reap_node
cp "$VOUT/lifecycle-junit.xml" /logs/verifier/lifecycle-junit.xml 2>/dev/null || true
cat /logs/verifier/lifecycle.log
python3 /tests/check_junit.py /logs/verifier/lifecycle-junit.xml lifecycle || lifecycle_integrity_rc=$?

as_node 'rm -rf test/__verifier__' || true
rm -f "$SNAP_INDEX"
# Final reap so no candidate-spawned process can rewrite the reward after this point.
reap_node
reward=0
if [ "$contract_rc" -eq 0 ] && [ "$contract_integrity_rc" -eq 0 ] \
   && [ "$lifecycle_rc" -eq 0 ] && [ "$lifecycle_integrity_rc" -eq 0 ] \
   && [ "$p2p_check_rc" -eq 0 ] && [ "$scope_rc" -eq 0 ]; then
  reward=1
fi
printf '%s\n' "$reward" > /logs/verifier/reward.txt
printf '{"reward":%s,"command_exit_code":%s,"contract_exit_code":%s,"contract_integrity_exit_code":%s,"lifecycle_exit_code":%s,"lifecycle_integrity_exit_code":%s,"pass_to_pass_exit_code":%s,"pass_to_pass_check_exit_code":%s,"scope_exit_code":%s}\n' \
  "$reward" "$((1-reward))" "$contract_rc" "$contract_integrity_rc" "$lifecycle_rc" "$lifecycle_integrity_rc" "$p2p_rc" "$p2p_check_rc" "$scope_rc" > /logs/verifier/reward.json
exit 0
