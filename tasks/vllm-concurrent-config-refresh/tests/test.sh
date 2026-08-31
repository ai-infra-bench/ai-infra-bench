#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
cd /workspace/vllm

pytest_rc=0
integrity_rc=0
startup_rc=0
invalid_rc=0
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 HF_HUB_OFFLINE=1 timeout 600 \
  pytest --noconftest -c /dev/null --rootdir=/workspace/vllm \
    -p no:cacheprovider -v -s --junitxml=/logs/verifier/junit.xml \
    /tests/test_regression.py || pytest_rc=$?
python /tests/check_junit.py /logs/verifier/junit.xml || integrity_rc=$?
if [ "$pytest_rc" -eq 0 ] && [ "$integrity_rc" -eq 0 ]; then
  timeout 240 /bin/bash /tests/test_four_api_startup.sh \
    > /logs/verifier/four_api_probe.log 2>&1 || startup_rc=$?
  cat /logs/verifier/four_api_probe.log
  timeout 150 python /tests/test_invalid_startup.py \
    > /logs/verifier/invalid_startup_probe.log 2>&1 || invalid_rc=$?
  cat /logs/verifier/invalid_startup_probe.log
fi
if [ "$pytest_rc" -eq 0 ] && [ "$integrity_rc" -eq 0 ] \
    && [ "$startup_rc" -eq 0 ] && [ "$invalid_rc" -eq 0 ]; then
  rc=0
  printf '1\n' > /logs/verifier/reward.txt
else
  rc=1
  printf '0\n' > /logs/verifier/reward.txt
fi
printf '{"reward":%s,"command_exit_code":%s,"pytest_exit_code":%s,"integrity_exit_code":%s,"startup_exit_code":%s,"invalid_exit_code":%s}\n' \
  "$([ "$rc" -eq 0 ] && printf 1 || printf 0)" "$rc" "$pytest_rc" \
  "$integrity_rc" "$startup_rc" "$invalid_rc" > /logs/verifier/reward.json
exit 0
