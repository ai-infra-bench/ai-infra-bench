#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
cd /workspace/vllm
rm -f /logs/verifier/{reward.txt,reward.json,private-junit.xml,upstream-junit.xml}

private_rc=0
private_integrity_rc=0
upstream_rc=0

export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
timeout 600 pytest --noconftest -c /dev/null --rootdir=/workspace/vllm \
  -p no:cacheprovider -v --junitxml=/logs/verifier/private-junit.xml \
  /tests/test_cohere_required_tools.py || private_rc=$?
python /tests/check_junit.py /logs/verifier/private-junit.xml 20 \
  || private_integrity_rc=$?

timeout 1200 pytest \
  tests/entrypoints/cohere/test_protocol.py \
  tests/entrypoints/cohere/test_api_router.py \
  tests/entrypoints/cohere/test_serving_conversion.py \
  --confcutdir=tests/entrypoints/cohere -q \
  --junitxml=/logs/verifier/upstream-junit.xml || upstream_rc=$?

reward=0
if [ "$private_rc" -eq 0 ] \
  && [ "$private_integrity_rc" -eq 0 ] \
  && [ "$upstream_rc" -eq 0 ]; then
  reward=1
fi

printf '%s\n' "$reward" > /logs/verifier/reward.txt
printf '{"reward":%s,"command_exit_code":%s,"private_exit_code":%s,"private_integrity_exit_code":%s,"upstream_exit_code":%s}\n' \
  "$reward" "$((1-reward))" "$private_rc" "$private_integrity_rc" "$upstream_rc" \
  > /logs/verifier/reward.json
exit 0
