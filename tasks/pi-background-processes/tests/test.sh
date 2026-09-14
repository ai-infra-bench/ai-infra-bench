#!/usr/bin/env bash
# Verifier entrypoint. Copies verifier-owned tests into the workspace test tree
# so vitest resolves workspace aliases, then requires every inventoried case to
# complete. A successful process exit is never sufficient on its own.
set -uo pipefail
mkdir -p /logs/verifier
rm -f /logs/verifier/{reward.txt,reward.json,contract-junit.xml,lifecycle-junit.xml,contract-summary.json,lifecycle-summary.json}
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
export HOME=/tmp/pi-verifier-home
mkdir -p "$HOME"
cd /workspace/pi/packages/coding-agent
rm -rf test/__verifier__

contract_rc=0
contract_integrity_rc=0
lifecycle_rc=0
lifecycle_integrity_rc=0
p2p_rc=0
p2p_check_rc=0

# Snapshot of what the agent changed, for review of real rollouts (never affects reward).
{
  git -C /workspace/pi status --short --untracked-files=all
  echo "--- diff vs Base (tracked + untracked, excluding node_modules/dist) ---"
  git -C /workspace/pi add -N --all -- . ':!**/node_modules/**' ':!**/dist/**' 2>/dev/null || true
  git -C /workspace/pi diff d981de1229ef899957bbe968bc8dcda02a21f477 -- . ':!**/node_modules/**' ':!**/dist/**' 2>/dev/null | head -c 4000000
  git -C /workspace/pi reset -q 2>/dev/null || true
} > /logs/verifier/agent-changes.patch 2>&1 || true

# PASS_TO_PASS: pi's own coding-agent suite must match the Base baseline recorded
# in the image, and existing test files must be untouched (new files are fine).
if ! git -C /workspace/pi diff --quiet d981de1229ef899957bbe968bc8dcda02a21f477 -- packages/coding-agent/test; then
  echo "PASS_TO_PASS: existing test files were modified" | tee /logs/verifier/pass-to-pass.log
  git -C /workspace/pi diff --name-only d981de1229ef899957bbe968bc8dcda02a21f477 -- packages/coding-agent/test | tee -a /logs/verifier/pass-to-pass.log
  p2p_check_rc=1
else
  timeout 900 node ../../node_modules/vitest/vitest.mjs run --retry 2 --maxWorkers=4 --reporter=junit --outputFile=/logs/verifier/pass-to-pass-junit.xml \
    > /logs/verifier/pass-to-pass.log 2>&1 || p2p_rc=$?
  tail -n 20 /logs/verifier/pass-to-pass.log
  # The baseline lives in the agent-writable image; check_pass_to_pass.py verifies it
  # against pins (Base case inventory, key-gated skipped set, failure cap) that hold
  # across image builds and platforms, so a rewritten baseline is rejected.
  python3 /tests/check_pass_to_pass.py /opt/pi-baseline/coding-agent-junit.xml /logs/verifier/pass-to-pass-junit.xml /tests/baseline-pins.json || p2p_check_rc=$?
fi

mkdir -p test/__verifier__
cp /tests/bg_support.ts /tests/bg.contract.test.ts /tests/bg.lifecycle.test.ts test/__verifier__/

NODE_OPTIONS=--expose-gc timeout 900 node ../../node_modules/vitest/vitest.mjs run --reporter=junit --outputFile=/logs/verifier/contract-junit.xml \
  test/__verifier__/bg.contract.test.ts > /logs/verifier/contract.log 2>&1 || contract_rc=$?
cat /logs/verifier/contract.log
python3 /tests/check_junit.py /logs/verifier/contract-junit.xml contract || contract_integrity_rc=$?

timeout 600 node ../../node_modules/vitest/vitest.mjs run --reporter=junit --outputFile=/logs/verifier/lifecycle-junit.xml \
  test/__verifier__/bg.lifecycle.test.ts > /logs/verifier/lifecycle.log 2>&1 || lifecycle_rc=$?
cat /logs/verifier/lifecycle.log
python3 /tests/check_junit.py /logs/verifier/lifecycle-junit.xml lifecycle || lifecycle_integrity_rc=$?

rm -rf test/__verifier__
reward=0
if [ "$contract_rc" -eq 0 ] && [ "$contract_integrity_rc" -eq 0 ] \
   && [ "$lifecycle_rc" -eq 0 ] && [ "$lifecycle_integrity_rc" -eq 0 ] \
   && [ "$p2p_check_rc" -eq 0 ]; then
  reward=1
fi
printf '%s\n' "$reward" > /logs/verifier/reward.txt
printf '{"reward":%s,"command_exit_code":%s,"contract_exit_code":%s,"contract_integrity_exit_code":%s,"lifecycle_exit_code":%s,"lifecycle_integrity_exit_code":%s,"pass_to_pass_exit_code":%s,"pass_to_pass_check_exit_code":%s}\n' \
  "$reward" "$((1-reward))" "$contract_rc" "$contract_integrity_rc" "$lifecycle_rc" "$lifecycle_integrity_rc" "$p2p_rc" "$p2p_check_rc" > /logs/verifier/reward.json
exit 0
