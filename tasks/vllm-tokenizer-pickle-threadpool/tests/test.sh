#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
cd /workspace/vllm
pytest_rc=0
integrity_rc=0
process_rc=0
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 timeout 900 \
  pytest --noconftest -c /dev/null --rootdir=/workspace/vllm \
    -p no:cacheprovider -v -s --junitxml=/logs/verifier/junit.xml \
    /tests/test_regression.py || pytest_rc=$?
python /tests/check_junit.py /logs/verifier/junit.xml || integrity_rc=$?
timeout 300 python /tests/test_real_process_transfer.py \
  > /logs/verifier/real_process_transfer.log 2>&1 || process_rc=$?
cat /logs/verifier/real_process_transfer.log
if [ "$pytest_rc" -eq 0 ] && [ "$integrity_rc" -eq 0 ] && [ "$process_rc" -eq 0 ]; then reward=1; else reward=0; fi
printf '%s\n' "$reward" > /logs/verifier/reward.txt
printf '{"reward":%s,"pytest_exit_code":%s,"integrity_exit_code":%s,"process_exit_code":%s}\n' \
  "$reward" "$pytest_rc" "$integrity_rc" "$process_rc" > /logs/verifier/reward.json
exit 0
