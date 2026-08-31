#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
cd /workspace/vllm
unit_rc=0
api_rc=0
target=tests/entrypoints/anthropic/test_harbor_inline_system_template.py
cp /tests/test_regression.py "$target"
timeout 600 bash -lc "pytest -p no:cacheprovider -v -s $target" || unit_rc=$?
timeout 300 bash /tests/test_anthropic_sdk_e2e.sh || api_rc=$?
if [ "$unit_rc" -eq 0 ] && [ "$api_rc" -eq 0 ]; then
  reward=1
  rc=0
  printf '1\n' > /logs/verifier/reward.txt
else
  reward=0
  rc=1
  printf '0\n' > /logs/verifier/reward.txt
fi
printf '{"reward":%s,"command_exit_code":%s,"unit_exit_code":%s,"api_exit_code":%s}\n' \
  "$reward" "$rc" "$unit_rc" "$api_rc" > /logs/verifier/reward.json
exit 0
