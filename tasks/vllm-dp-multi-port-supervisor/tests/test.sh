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
if cd /workspace/repo && "$python_bin" -I /tests/verify_dp_supervisor.py; then
  printf '1\n' > /logs/verifier/reward.txt
else
  printf '0\n' > /logs/verifier/reward.txt
fi
