#!/usr/bin/env bash
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo 'verifier setup must run as root' >&2; exit 1; }
mkdir -p /logs/verifier
printf '0\n' > /logs/verifier/reward.txt
python_bin=
for candidate in /opt/venv/bin/python /usr/local/bin/python /usr/local/bin/python3 /usr/bin/python3; do
    if [ -x "$candidate" ] && [ "$(stat -Lc '%U:%G' "$candidate")" = 'root:root' ]; then
        python_bin="$candidate"
        break
    fi
done
[ -n "$python_bin" ] || { echo 'trusted Python unavailable' >&2; exit 1; }
# A read-only harness mount may have a non-root host UID. Stage only trusted
# harness files; no candidate module is loaded until after dropping privileges.
stage="$(mktemp -d /tmp/mm-merge-verifier.XXXXXXXX)"
trap 'rm -rf -- "$stage"' EXIT
for file in supervise_verifier.py verify_multimodal_merge.py case_specs.py checkpoint.c; do
    install -o 0 -g 0 -m 0644 "/tests/$file" "$stage/$file"
done
python_include="$("$python_bin" -I -c 'import sysconfig; print(sysconfig.get_path("include"))')"
/usr/bin/cc -O2 -shared -fPIC -fvisibility=hidden -I"$python_include" "$stage/checkpoint.c" -o "$stage/_checkpoint.so"
chmod 0755 "$stage"
"$python_bin" -I "$stage/supervise_verifier.py"
