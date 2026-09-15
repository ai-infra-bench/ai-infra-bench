#!/usr/bin/env bash
# The candidate never determines reward. Python checks exact independent case
# inventories and the NEW Base suite outcomes after real SDK tests finish.
set -uo pipefail
export PI_WORKSPACE=/workspace/pi PI_OFFLINE=1 PI_TELEMETRY=0 PI_NO_LOCAL_LLM=1
mkdir -p /logs/verifier
if [ "$(id -u)" -ne 0 ] || [ -L /logs/verifier ]; then exit 1; fi
find /logs/verifier -type l -delete
chown -R root:root /logs/verifier
chmod -R go-w /logs/verifier
chmod 0755 /logs/verifier
umask 022
trusted_tests=$(mktemp -d /opt/pi-plan-verifier.XXXXXXXX)
cp -R /tests/. "$trusted_tests/"
chown -R root:root "$trusted_tests"
chmod -R a-w,a+rX "$trusted_tests"
export PI_TRUSTED_TESTS="$trusted_tests"
export NODE_OPTIONS="--require=$trusted_tests/drop_worker.cjs"
printf '0\n' > /logs/verifier/reward.txt
rm -f /logs/verifier/contract-junit.xml /logs/verifier/lifecycle-junit.xml /logs/verifier/pass-to-pass-junit.xml /logs/verifier/reward.json /logs/verifier/pass-to-pass-summary.json /logs/verifier/pass-to-pass-check.log /logs/verifier/contract-check.log /logs/verifier/lifecycle-check.log
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_OAUTH_TOKEN OPENAI_API_KEY GEMINI_API_KEY GOOGLE_CLOUD_API_KEY GROQ_API_KEY CEREBRAS_API_KEY XAI_API_KEY OPENROUTER_API_KEY ZAI_API_KEY ZAI_CODING_CN_API_KEY MISTRAL_API_KEY MINIMAX_API_KEY MINIMAX_CN_API_KEY AI_GATEWAY_API_KEY OPENCODE_API_KEY COPILOT_GITHUB_TOKEN GH_TOKEN GITHUB_TOKEN HF_TOKEN DEEPSEEK_API_KEY FIREWORKS_API_KEY KIMI_API_KEY MOONSHOT_API_KEY NVIDIA_API_KEY TOGETHER_API_KEY BASETEN_API_KEY CLOUDFLARE_API_KEY RADIUS_API_KEY ANT_LING_API_KEY XIAOMI_API_KEY XIAOMI_TOKEN_PLAN_AMS_API_KEY XIAOMI_TOKEN_PLAN_CN_API_KEY XIAOMI_TOKEN_PLAN_SGP_API_KEY QWEN_TOKEN_PLAN_API_KEY QWEN_TOKEN_PLAN_CN_API_KEY AZURE_OPENAI_API_KEY AZURE_OPENAI_BASE_URL AZURE_OPENAI_RESOURCE_NAME GOOGLE_APPLICATION_CREDENTIALS GOOGLE_CLOUD_PROJECT GCLOUD_PROJECT GOOGLE_CLOUD_LOCATION AWS_PROFILE AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_REGION AWS_DEFAULT_REGION AWS_BEARER_TOKEN_BEDROCK AWS_CONTAINER_CREDENTIALS_RELATIVE_URI AWS_CONTAINER_CREDENTIALS_FULL_URI AWS_WEB_IDENTITY_TOKEN_FILE
cd /workspace/pi/packages/coding-agent || exit 0
scope_rc=0; p2p_rc=0; p2p_check_rc=0; contract_rc=0; contract_check_rc=0; lifecycle_rc=0; lifecycle_check_rc=0; integrity_rc=0
python3 "$trusted_tests/test_integrity.py" > /logs/verifier/integrity.log 2>&1 || integrity_rc=$?
python3 "$trusted_tests/check_scope.py" /workspace/pi > /logs/verifier/scope.json 2>&1 || scope_rc=$?
# Never let the root coordinator load a modified configuration or core module.
if [ "$scope_rc" -ne 0 ] || [ "$integrity_rc" -ne 0 ]; then
  printf '{"reward":0,"scope_exit_code":%s,"integrity_exit_code":%s}\n' "$scope_rc" "$integrity_rc" > /logs/verifier/reward.json
  cat /logs/verifier/reward.json
  exit 0
fi
# Freeze allowed candidate directories after scope validation. This prevents a
# leftover candidate process from replacing a tested file while grading runs.
chown -hR root:root /workspace/pi/packages/coding-agent/examples/extensions/plan-mode /workspace/pi/packages/coding-agent/test
find /workspace/pi/packages/coding-agent/examples/extensions/plan-mode /workspace/pi/packages/coding-agent/test -type d -exec chmod go-w {} +
find /workspace/pi/packages/coding-agent/examples/extensions/plan-mode /workspace/pi/packages/coding-agent/test -type f -exec chmod go-w {} +
# Candidate-writable Vite caches must not enter the root coordinator.
rm -rf /workspace/pi/packages/coding-agent/node_modules/.vite /workspace/pi/packages/coding-agent/node_modules/.vite-temp
mkdir -p /workspace/pi/packages/coding-agent/node_modules/.vite /workspace/pi/packages/coding-agent/node_modules/.vite-temp
chown root:root /workspace/pi/packages/coding-agent/node_modules/.vite /workspace/pi/packages/coding-agent/node_modules/.vite-temp
chmod 0755 /workspace/pi/packages/coding-agent/node_modules/.vite /workspace/pi/packages/coding-agent/node_modules/.vite-temp
# The frozen original SettingsManager tests create/remove cwd-local scratch
# directories. Sticky permissions allow only their worker-owned scratch entries
# to be removed; root-owned configuration and source entries remain protected.
chown root:root /workspace/pi/packages/coding-agent
chmod 1777 /workspace/pi/packages/coding-agent
# Select only original Base test files; permitted candidate-added tests do not
# alter the old-suite inventory. The four intentionally changed plan extension
# tests are excluded; existing plan utility tests remain in this list.
mapfile -t old_tests < "$trusted_tests/p2p-files.txt"
timeout 900 node ../../node_modules/vitest/vitest.mjs run --config /workspace/pi/packages/coding-agent/vitest.config.ts --pool=forks --retry 2 --maxWorkers=4 --reporter=junit --outputFile=/logs/verifier/pass-to-pass-junit.xml "${old_tests[@]}" > /logs/verifier/pass-to-pass.log 2>&1 || p2p_rc=$?
python3 "$trusted_tests/check_pass_to_pass.py" /opt/pi-baseline/coding-agent-junit.xml /logs/verifier/pass-to-pass-junit.xml "$trusted_tests/baseline-pins.json" > /logs/verifier/pass-to-pass-check.log 2>&1 || p2p_check_rc=$?
mkdir -p test/__plan_verifier__/fixtures
cp "$trusted_tests/plan_support.mjs" "$trusted_tests/plan.contract.test.ts" "$trusted_tests/plan.lifecycle.test.ts" test/__plan_verifier__/
cp "$trusted_tests/fixtures/plan_child.mjs" test/__plan_verifier__/fixtures/
chown -R root:root test/__plan_verifier__
chmod -R a-w,a+rX test/__plan_verifier__
timeout 600 node ../../node_modules/vitest/vitest.mjs run --config /workspace/pi/packages/coding-agent/vitest.config.ts --pool=forks --reporter=junit --outputFile=/logs/verifier/contract-junit.xml test/__plan_verifier__/plan.contract.test.ts > /logs/verifier/contract.log 2>&1 || contract_rc=$?
python3 "$trusted_tests/check_junit.py" /logs/verifier/contract-junit.xml contract > /logs/verifier/contract-check.log 2>&1 || contract_check_rc=$?
timeout 300 node ../../node_modules/vitest/vitest.mjs run --config /workspace/pi/packages/coding-agent/vitest.config.ts --pool=forks --reporter=junit --outputFile=/logs/verifier/lifecycle-junit.xml test/__plan_verifier__/plan.lifecycle.test.ts > /logs/verifier/lifecycle.log 2>&1 || lifecycle_rc=$?
python3 "$trusted_tests/check_junit.py" /logs/verifier/lifecycle-junit.xml lifecycle > /logs/verifier/lifecycle-check.log 2>&1 || lifecycle_check_rc=$?
rm -rf test/__plan_verifier__
reward=0
if [ "$integrity_rc" -eq 0 ] && [ "$scope_rc" -eq 0 ] && [ "$p2p_check_rc" -eq 0 ] && [ "$contract_rc" -eq 0 ] && [ "$contract_check_rc" -eq 0 ] && [ "$lifecycle_rc" -eq 0 ] && [ "$lifecycle_check_rc" -eq 0 ]; then reward=1; fi
printf '%s\n' "$reward" > /logs/verifier/reward.txt
printf '{"reward":%s,"scope_exit_code":%s,"pass_to_pass_exit_code":%s,"pass_to_pass_check_exit_code":%s,"contract_exit_code":%s,"contract_integrity_exit_code":%s,"lifecycle_exit_code":%s,"lifecycle_integrity_exit_code":%s}\n' "$reward" "$scope_rc" "$p2p_rc" "$p2p_check_rc" "$contract_rc" "$contract_check_rc" "$lifecycle_rc" "$lifecycle_check_rc" > /logs/verifier/reward.json
cat /logs/verifier/reward.json
exit 0
