#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
printf '0\n' > /logs/verifier/reward.txt
cd /workspace/vllm

compile_rc=0
regression_rc=0
pytest_rc=0
integrity_rc=0
timeout 1800 cargo build --locked --offline --release --manifest-path /workspace/vllm/rust/Cargo.toml \
  -p vllm-cmd --bin vllm-rs > /logs/verifier/build.log 2>&1 || compile_rc=$?

if [ "$compile_rc" -eq 0 ]; then
  timeout 1200 cargo test --locked --offline --release --manifest-path /workspace/vllm/rust/Cargo.toml \
    -p vllm-server -p vllm-chat --lib -- --test-threads=2 \
    > /logs/verifier/rust-regression.log 2>&1 || regression_rc=$?
  if [ "$regression_rc" -eq 0 ]; then
    python /tests/check_rust_regressions.py /logs/verifier/rust-regression.log || regression_rc=$?
  fi
  export DERENDER_RUST_BINARY=/workspace/vllm/rust/target/release/vllm-rs
  export DERENDER_TEST_FRONTEND=rust
  PYTHONPATH=/tests PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 timeout 1200 \
    pytest --noconftest -c /dev/null --rootdir=/workspace/vllm \
      -p no:cacheprovider -p verifier_support -v -s \
      --junitxml=/logs/verifier/derender.xml \
      /tests/test_derender_http.py /tests/test_derender_stream.py \
      /tests/test_derender_parsing.py || pytest_rc=$?
  python /tests/check_junit.py /logs/verifier/derender.xml 49 || integrity_rc=$?
else
  cat /logs/verifier/build.log
  pytest_rc=1
  regression_rc=1
  integrity_rc=1
fi

reward=0
if [ "$compile_rc" -eq 0 ] && [ "$regression_rc" -eq 0 ] && [ "$pytest_rc" -eq 0 ] && [ "$integrity_rc" -eq 0 ]; then
  reward=1
fi
printf '%s\n' "$reward" > /logs/verifier/reward.txt
printf '{"reward":%s,"compile_exit_code":%s,"regression_exit_code":%s,"pytest_exit_code":%s,"integrity_exit_code":%s}\n' \
  "$reward" "$compile_rc" "$regression_rc" "$pytest_rc" "$integrity_rc" > /logs/verifier/reward.json
