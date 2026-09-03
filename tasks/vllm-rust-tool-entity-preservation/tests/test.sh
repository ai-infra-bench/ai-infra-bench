#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
cd /workspace/vllm

build_rc=0
source_tests_rc=0
pytest_rc=0
integrity_rc=0
rust_rc=0
opencode_rc=0
mkdir -p rust/src/tool-parser/examples
cp /tests/tool_parser_probe.rs \
  rust/src/tool-parser/examples/ai_infra_probe.rs
timeout 600 cargo build --quiet --manifest-path rust/Cargo.toml \
  -p vllm-tool-parser --example ai_infra_probe || build_rc=$?
if [ "$build_rc" -eq 0 ]; then
  timeout 600 cargo test --quiet --manifest-path rust/Cargo.toml \
    -p vllm-tool-parser --no-run || source_tests_rc=$?
else
  source_tests_rc=1
fi
export AI_INFRA_TOOL_PROBE=/workspace/vllm/rust/target/debug/examples/ai_infra_probe

if [ "$build_rc" -eq 0 ] && [ "$source_tests_rc" -eq 0 ]; then
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 timeout 600 \
    pytest --noconftest -c /dev/null --rootdir=/workspace/vllm \
      -p no:cacheprovider -v -s --junitxml=/logs/verifier/junit.xml \
      /tests/test_regression.py || pytest_rc=$?
  python /tests/check_junit.py /logs/verifier/junit.xml || integrity_rc=$?
  timeout 180 python /tests/test_real_rust_matrix.py \
    > /logs/verifier/real_rust_matrix.log 2>&1 || rust_rc=$?
  cat /logs/verifier/real_rust_matrix.log
  timeout 600 python /tests/test_real_opencode_edit.py \
    > /logs/verifier/real_opencode_edit.log 2>&1 || opencode_rc=$?
  cat /logs/verifier/real_opencode_edit.log
else
  pytest_rc=1
  integrity_rc=1
  rust_rc=1
  opencode_rc=1
fi

if [ "$build_rc" -eq 0 ] && [ "$pytest_rc" -eq 0 ] \
  && [ "$source_tests_rc" -eq 0 ] \
  && [ "$integrity_rc" -eq 0 ] && [ "$rust_rc" -eq 0 ] \
  && [ "$opencode_rc" -eq 0 ]; then
  reward=1
else
  reward=0
fi
printf '%s\n' "$reward" > /logs/verifier/reward.txt
printf '{"reward":%s,"build_exit_code":%s,"source_tests_exit_code":%s,"pytest_exit_code":%s,"integrity_exit_code":%s,"rust_exit_code":%s,"opencode_exit_code":%s}\n' \
  "$reward" "$build_rc" "$source_tests_rc" "$pytest_rc" "$integrity_rc" "$rust_rc" "$opencode_rc" \
  > /logs/verifier/reward.json
exit 0
