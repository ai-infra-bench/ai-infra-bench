#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
cd /workspace/vllm
pytest_rc=0
integrity_rc=0
e2e_rc=0
target=tests/v1/core/test_harbor_async_spec_placeholder_discard.py
cp /tests/test_regression.py "$target"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 timeout 600 \
  pytest --noconftest -c /dev/null --rootdir=/workspace/vllm \
    -p no:cacheprovider -v -s --junitxml=/logs/verifier/junit.xml "$target" \
  || pytest_rc=$?
python /tests/check_junit.py /logs/verifier/junit.xml || integrity_rc=$?
timeout 120 python /tests/test_real_reset_lifecycle.py \
  > /logs/verifier/real_reset_lifecycle.log 2>&1 || e2e_rc=$?
cat /logs/verifier/real_reset_lifecycle.log
if [ "$pytest_rc" -eq 0 ] && [ "$integrity_rc" -eq 0 ] \
    && [ "$e2e_rc" -eq 0 ]; then
  rc=0
  printf '1\n' > /logs/verifier/reward.txt
else
  rc=1
  printf '0\n' > /logs/verifier/reward.txt
fi
printf '{"reward":%s,"command_exit_code":%s,"pytest_exit_code":%s,"integrity_exit_code":%s,"e2e_exit_code":%s}\n' \
  "$([ "$rc" -eq 0 ] && printf 1 || printf 0)" "$rc" "$pytest_rc" \
  "$integrity_rc" "$e2e_rc" > /logs/verifier/reward.json
exit 0
