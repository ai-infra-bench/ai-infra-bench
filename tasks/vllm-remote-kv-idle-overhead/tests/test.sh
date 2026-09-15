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
trusted_dir="$(mktemp -d /tmp/ai-infra-verifier.XXXXXXXX)"
trap 'rm -rf -- "$trusted_dir"' EXIT
install -o root -g root -m 0644 /tests/supervise_verifier.py "$trusted_dir/supervise_verifier.py"
install -o root -g root -m 0644 /tests/checkpoint.c "$trusted_dir/checkpoint.c"
install -o root -g root -m 0644 /tests/verify_blocked_waiting.py "$trusted_dir/worker.py"
python_include="$("$python_bin" -I -c 'import sysconfig; print(sysconfig.get_path("include"))')"
compiler="$(command -v cc || command -v gcc)"
"$compiler" -O2 -shared -fPIC -fvisibility=hidden -I"$python_include" \
  "$trusted_dir/checkpoint.c" -o "$trusted_dir/_checkpoint.so"
chmod 0755 "$trusted_dir"
exec "$python_bin" -I "$trusted_dir/supervise_verifier.py" \
  "$python_bin" "$trusted_dir/worker.py" 600
