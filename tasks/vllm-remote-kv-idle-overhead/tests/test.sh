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
test -n "$python_bin"
trusted_dir="$(mktemp -d /tmp/ai-infra-verifier.XXXXXXXX)"
trap 'rm -rf -- "$trusted_dir"' EXIT
for name in supervise_verifier.py checkpoint.c verify_blocked_waiting.py worker.py fixtures.py nixl_behavior.py nixl_io.py; do
  install -o root -g root -m 0644 "/tests/$name" "$trusted_dir/$name"
done
python_include="$("$python_bin" -I -S -c 'import sysconfig; print(sysconfig.get_path("include"))')"
compiler="$(command -v cc || command -v gcc)"
"$compiler" -O2 -shared -fPIC -fvisibility=hidden -pthread -I"$python_include" \
  "$trusted_dir/checkpoint.c" -o "$trusted_dir/_checkpoint.so"
chmod 0755 "$trusted_dir"
"$python_bin" -I -S "$trusted_dir/supervise_verifier.py" 900
