#!/usr/bin/env bash
set -euo pipefail
mkdir -p /logs/verifier
printf '0\n' > /logs/verifier/reward.txt
printf '{"reward": 0}\n' > /logs/verifier/reward.json
python_bin=""
for candidate in /opt/venv/bin/python /usr/local/bin/python /usr/local/bin/python3 /usr/bin/python3; do
  if [ -x "$candidate" ] && [ "$(stat -Lc '%U:%G' "$candidate")" = "root:root" ]; then
    python_bin="$candidate"
    break
  fi
done
if [ -z "$python_bin" ]; then
  exit 0
fi
stage=/opt/ai-infra-verifier
mkdir -p "$stage"
install -m 0600 -o 0 -g 0 /tests/supervise_verifier.py "$stage/supervise_verifier.py"
install -m 0600 -o 0 -g 0 /tests/verify_connector_lifecycle.py "$stage/verify_connector_lifecycle.py"
install -m 0644 -o 0 -g 0 /tests/connector_worker.py "$stage/connector_worker.py"
exec "$python_bin" -I "$stage/supervise_verifier.py" "$python_bin" /workspace/repo 900
