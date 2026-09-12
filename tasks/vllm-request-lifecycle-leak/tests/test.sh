#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
  echo "verifier setup must run as root" >&2
  exit 1
fi
python_bin=
for candidate in /opt/venv/bin/python /usr/local/bin/python /usr/local/bin/python3 /usr/bin/python3; do
  if [ -x "$candidate" ] && [ "$(stat -Lc '%U:%G' "$candidate")" = "root:root" ]; then
    python_bin="$candidate"
    break
  fi
done
if [ -z "$python_bin" ]; then
  echo "trusted verifier Python is unavailable" >&2
  exit 1
fi
cd /workspace/repo
# /tests is a trusted read-only harness mount, but its host UID need not be 0.
# Stage only the harness scripts before any candidate code is executed.
trusted_dir="$(mktemp -d /tmp/retention-verifier.XXXXXXXX)"
trap 'rm -rf -- "$trusted_dir"' EXIT
install -o root -g root -m 0644 /tests/supervise_retention.py "$trusted_dir/supervise_retention.py"
install -o root -g root -m 0644 /tests/verify_retention.py "$trusted_dir/verify_retention.py"
chmod 0755 "$trusted_dir"
"$python_bin" -I "$trusted_dir/supervise_retention.py" "$python_bin"
