#!/usr/bin/env bash
set -uo pipefail

mkdir -p /logs/verifier
cd /workspace/vllm

inject_rc=0
compile_rc=0
fixture_rc=0
fixture_integrity_rc=0
python_control_rc=0
rust_matrix_rc=0
rust_integrity_rc=0

cp /tests/vllm_server_http_harness.rs \
  rust/src/server/src/routes/ai_infra_anthropic_http.rs || inject_rc=$?
if [ "$inject_rc" -eq 0 ]; then
  printf '\n#[cfg(test)]\nmod ai_infra_anthropic_http;\n' >> \
    rust/src/server/src/routes.rs || inject_rc=$?
fi

if [ "$inject_rc" -eq 0 ]; then
  timeout 1800 cargo test --quiet --manifest-path rust/Cargo.toml \
    -p vllm-server ai_infra_anthropic_http_server --no-run || compile_rc=$?
else
  compile_rc=1
fi

PYTHONPATH=/tests PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 timeout 300 \
  pytest --noconftest -c /dev/null --rootdir=/workspace/vllm \
    -p no:cacheprovider -p pytest_asyncio.plugin -v -s \
    --junitxml=/logs/verifier/sdk_fixture.xml \
    /tests/test_sdk_fixture.py || fixture_rc=$?
python /tests/check_junit.py /logs/verifier/sdk_fixture.xml 17 \
  || fixture_integrity_rc=$?

timeout 360 python /tests/python_frontend_control.py \
  > /logs/verifier/python_frontend_control.log 2>&1 || python_control_rc=$?
cat /logs/verifier/python_frontend_control.log

if [ "$compile_rc" -eq 0 ]; then
  PYTHONPATH=/tests PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 timeout 1800 \
    pytest --noconftest -c /dev/null --rootdir=/workspace/vllm \
      -p no:cacheprovider -p pytest_asyncio.plugin -v -s \
      --junitxml=/logs/verifier/rust_sdk_matrix.xml \
      /tests/test_rust_sdk_matrix.py \
      /tests/test_rust_request_matrix.py \
      /tests/test_rust_historical_regressions.py || rust_matrix_rc=$?
  python /tests/check_junit.py /logs/verifier/rust_sdk_matrix.xml 69 \
    || rust_integrity_rc=$?
else
  rust_matrix_rc=1
  rust_integrity_rc=1
fi

if [ "$inject_rc" -eq 0 ] && [ "$compile_rc" -eq 0 ] \
  && [ "$fixture_rc" -eq 0 ] && [ "$fixture_integrity_rc" -eq 0 ] \
  && [ "$python_control_rc" -eq 0 ] \
  && [ "$rust_matrix_rc" -eq 0 ] && [ "$rust_integrity_rc" -eq 0 ]; then
  reward=1
else
  reward=0
fi

printf '%s\n' "$reward" > /logs/verifier/reward.txt
printf '{"reward":%s,"inject_exit_code":%s,"compile_exit_code":%s,"sdk_fixture_exit_code":%s,"sdk_fixture_integrity_exit_code":%s,"python_control_exit_code":%s,"rust_matrix_exit_code":%s,"rust_integrity_exit_code":%s}\n' \
  "$reward" "$inject_rc" "$compile_rc" "$fixture_rc" \
  "$fixture_integrity_rc" "$python_control_rc" "$rust_matrix_rc" \
  "$rust_integrity_rc" > /logs/verifier/reward.json
exit 0
