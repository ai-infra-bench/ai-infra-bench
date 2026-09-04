#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
cd /workspace/vllm
python_bin=/usr/local/bin/python

if [ ! -x "$python_bin" ] || [ "$(stat -c '%U:%G' "$python_bin")" != "root:root" ]; then
  printf '0\n' > /logs/verifier/reward.txt
  printf '{"reward":0,"command_exit_code":1,"integrity_exit_code":1}\n' \
    > /logs/verifier/reward.json
  exit 0
fi

pytest_rc=0
integrity_rc=0
lifecycle_rc=0
server_rc=0
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 timeout 900 \
  "$python_bin" -I -m pytest --noconftest -c /dev/null --rootdir=/workspace/vllm \
    -p no:cacheprovider -v -s --junitxml=/logs/verifier/junit.xml \
    /tests/test_regression.py || pytest_rc=$?
test -s /logs/verifier/junit.xml || integrity_rc=$?
"$python_bin" -I /tests/check_junit.py /logs/verifier/junit.xml || integrity_rc=$?
timeout 240 "$python_bin" -I /tests/test_real_scheduler_lifecycle.py \
  > /logs/verifier/real_scheduler_lifecycle.log 2>&1 || lifecycle_rc=$?
cat /logs/verifier/real_scheduler_lifecycle.log
test -s /logs/verifier/real_scheduler_lifecycle.log || lifecycle_rc=$?
timeout 360 "$python_bin" -I /tests/test_real_cpu_server.py \
  > /logs/verifier/real_cpu_server_probe.log 2>&1 || server_rc=$?
cat /logs/verifier/real_cpu_server_probe.log
test -s /logs/verifier/real_cpu_server_probe.log || server_rc=$?
if [ "$pytest_rc" -eq 0 ] && [ "$integrity_rc" -eq 0 ] \
    && [ "$lifecycle_rc" -eq 0 ] && [ "$server_rc" -eq 0 ]; then
  rc=0
  printf '1\n' > /logs/verifier/reward.txt
else
  rc=1
  printf '0\n' > /logs/verifier/reward.txt
fi
printf '{"reward":%s,"command_exit_code":%s,"pytest_exit_code":%s,"integrity_exit_code":%s,"lifecycle_exit_code":%s,"server_exit_code":%s}\n' \
  "$([ "$rc" -eq 0 ] && printf 1 || printf 0)" "$rc" "$pytest_rc" \
  "$integrity_rc" "$lifecycle_rc" "$server_rc" > /logs/verifier/reward.json
exit 0
