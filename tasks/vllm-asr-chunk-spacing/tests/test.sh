#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
cd /workspace/vllm
rm -f /logs/verifier/{reward.txt,reward.json,junit.xml,pipeline-junit.xml,regression-summary.json,pipeline-summary.json}
pytest_rc=0
integrity_rc=0
e2e_rc=0
pipeline_integrity_rc=0
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
timeout 600 pytest --noconftest -c /dev/null --rootdir=/workspace/vllm -p no:cacheprovider -p pytest_asyncio.plugin -v -s --junitxml=/logs/verifier/junit.xml /tests/test_regression.py || pytest_rc=$?
python /tests/check_junit.py /logs/verifier/junit.xml regression || integrity_rc=$?
timeout 180 python /tests/test_real_speech_pipeline.py > /logs/verifier/real_speech_pipeline.log 2>&1 || e2e_rc=$?
cat /logs/verifier/real_speech_pipeline.log
# A successful process exit is insufficient: require every pipeline assertion.
python /tests/check_junit.py /logs/verifier/pipeline-junit.xml pipeline || pipeline_integrity_rc=$?
reward=0
if [ "$pytest_rc" -eq 0 ] && [ "$integrity_rc" -eq 0 ] && [ "$e2e_rc" -eq 0 ] && [ "$pipeline_integrity_rc" -eq 0 ]; then
  reward=1
fi
printf '%s\n' "$reward" > /logs/verifier/reward.txt
printf '{"reward":%s,"command_exit_code":%s,"pytest_exit_code":%s,"integrity_exit_code":%s,"e2e_exit_code":%s,"pipeline_integrity_exit_code":%s}\n' \
  "$reward" "$((1-reward))" "$pytest_rc" "$integrity_rc" "$e2e_rc" "$pipeline_integrity_rc" > /logs/verifier/reward.json
exit 0
