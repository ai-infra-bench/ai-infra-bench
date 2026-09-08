#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
python_bin=
for candidate in /opt/venv/bin/python /usr/local/bin/python /usr/local/bin/python3 /usr/bin/python3; do
  if [ -x "$candidate" ] && [ "$(stat -Lc '%U:%G' "$candidate")" = "root:root" ]; then
    python_bin="$candidate"
    break
  fi
done
if [ -z "$python_bin" ]; then
  printf '0\n' > /logs/verifier/reward.txt
  exit 0
fi
stage=/opt/ai-infra-verifier
mkdir -p "$stage"
install -m 0644 -o 0 -g 0 /tests/supervise_verifier.py "$stage/supervise_verifier.py"
install -m 0644 -o 0 -g 0 /tests/verify_connector_lifecycle.py "$stage/verify_connector_lifecycle.py"
exec "$python_bin" -I "$stage/supervise_verifier.py" \
  "$python_bin" "$stage/verify_connector_lifecycle.py" /workspace/repo \
  "PASS: current consumer works and legacy lifecycle is rejected" 900
