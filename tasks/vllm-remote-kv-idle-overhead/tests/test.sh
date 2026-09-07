#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
python_bin=/opt/venv/bin/python
if [ ! -x "$python_bin" ]; then
  printf 'FAIL: expected task Python is missing: %s\n' "$python_bin" \
    | tee /logs/verifier/verifier.log
  printf '0\n' > /logs/verifier/reward.txt
  exit 0
fi
if ! "$python_bin" -I - <<'PY' | tee /logs/verifier/python-env.log; then
import sys
print(f"python={sys.executable}")
import torch
print(f"torch={torch.__version__}")
PY
  printf '0\n' > /logs/verifier/reward.txt
  exit 0
fi
stage=/opt/ai-infra-verifier
mkdir -p "$stage"
install -m 0644 -o 0 -g 0 /tests/supervise_verifier.py "$stage/supervise_verifier.py"
install -m 0644 -o 0 -g 0 /tests/verify_blocked_waiting.py "$stage/verify_blocked_waiting.py"
exec "$python_bin" -I "$stage/supervise_verifier.py" \
  "$python_bin" "$stage/verify_blocked_waiting.py" /app \
  "PASS: remote-KV waiting idle overhead is bounded" 600
