#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
cd /workspace/vllm

api_rc=0
integrity_rc=0
timeout 720 bash /tests/test_anthropic_sdk_e2e.sh \
  > /logs/verifier/anthropic_sdk_e2e.log 2>&1 || api_rc=$?
cat /logs/verifier/anthropic_sdk_e2e.log
if [ "$api_rc" -eq 0 ]; then
  python /tests/check_probe.py \
    /logs/verifier/official_qwen_probe.json \
    /logs/verifier/restrictive_sentinel_probe.json \
    /logs/verifier/permissive_probe.json || integrity_rc=$?
else
  integrity_rc=1
fi
if [ "$api_rc" -eq 0 ] && [ "$integrity_rc" -eq 0 ]; then
  reward=1
  rc=0
  printf '1\n' > /logs/verifier/reward.txt
else
  reward=0
  rc=1
  printf '0\n' > /logs/verifier/reward.txt
fi
printf '{"reward":%s,"command_exit_code":%s,"api_exit_code":%s,"integrity_exit_code":%s}\n' \
  "$reward" "$rc" "$api_rc" "$integrity_rc" > /logs/verifier/reward.json
exit 0
