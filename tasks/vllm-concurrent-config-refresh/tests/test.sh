#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
cd /workspace/vllm

rc=0
timeout 600 bash -lc \
  "pytest -p no:cacheprovider -v -s /tests/test_regression.py" || rc=$?

if [ "$rc" -eq 0 ]; then
  timeout 180 /bin/bash /tests/test_four_api_startup.sh || rc=$?
fi

if [ "$rc" -eq 0 ]; then
  printf '1\n' > /logs/verifier/reward.txt
else
  printf '0\n' > /logs/verifier/reward.txt
fi
printf '{"reward":%s,"command_exit_code":%s}\n' \
  "$([ "$rc" -eq 0 ] && printf 1 || printf 0)" "$rc" \
  > /logs/verifier/reward.json
exit 0
