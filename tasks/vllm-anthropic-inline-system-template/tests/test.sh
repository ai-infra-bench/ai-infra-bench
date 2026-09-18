#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
cd /workspace/vllm
rm -f /logs/verifier/reward.txt /logs/verifier/reward.json
api_rc=0
integrity_rc=0
timeout 1200 bash /tests/test_anthropic_sdk_e2e.sh \
  > /logs/verifier/anthropic_sdk_e2e.log 2>&1 || api_rc=$?
cat /logs/verifier/anthropic_sdk_e2e.log
# Check every required record even if the runner failed or exited early.
python /tests/check_probe.py /logs/verifier || integrity_rc=$?
if [ "$api_rc" -eq 0 ] && [ "$integrity_rc" -eq 0 ]; then
  reward=1
  rc=0
else
  reward=0
  rc=1
fi
printf '%s\n' "$reward" > /logs/verifier/reward.txt
printf '{"reward":%s,"command_exit_code":%s,"api_exit_code":%s,"integrity_exit_code":%s}\n' \
  "$reward" "$rc" "$api_rc" "$integrity_rc" > /logs/verifier/reward.json
exit 0
