#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
cd /workspace/vllm
pytest_rc=0; integrity_rc=0; pipeline_rc=0
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 timeout 600 pytest --noconftest -c /dev/null --rootdir=/workspace/vllm -p no:cacheprovider -v -s --junitxml=/logs/verifier/junit.xml /tests/test_regression.py /tests/test_scheduler_handoff.py /tests/test_padded_state_transfer.py || pytest_rc=$?
python /tests/check_junit.py /logs/verifier/junit.xml || integrity_rc=$?
timeout 180 python /tests/test_real_inmemory_pd_transfer.py > /logs/verifier/real_inmemory_pd_transfer.log 2>&1 || pipeline_rc=$?
cat /logs/verifier/real_inmemory_pd_transfer.log
if [ "$pytest_rc" -eq 0 ] && [ "$integrity_rc" -eq 0 ] && [ "$pipeline_rc" -eq 0 ]; then rc=0; printf '1\n' > /logs/verifier/reward.txt; else rc=1; printf '0\n' > /logs/verifier/reward.txt; fi
printf '{"reward":%s,"command_exit_code":%s,"pytest_exit_code":%s,"integrity_exit_code":%s,"pipeline_exit_code":%s}\n' "$([ "$rc" -eq 0 ] && printf 1 || printf 0)" "$rc" "$pytest_rc" "$integrity_rc" "$pipeline_rc" > /logs/verifier/reward.json
exit 0
