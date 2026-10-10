#!/bin/bash
set -u
umask 022
python3 -I - <<'PY'
import json
import os
from pathlib import Path
import stat

output = Path('/logs/verifier')
output_ready = False
try:
    for directory in (Path('/logs'), output):
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            raise RuntimeError('Verifier output must be a real directory')
        directory.mkdir(exist_ok=True)
        os.chown(directory, 0, 0)
        directory.chmod(0o755)
    output_ready = True
    for name in ('reward.txt', 'reward.json', 'grading-status.json', 'behavior/grading-status.json'):
        (output / name).unlink(missing_ok=True)

    # Harbor's normal directory upload preserves host ownership. Seal the
    # uploaded directory before protecting files and starting candidate Pi.
    directory = Path('/tests')
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fchown(descriptor, 0, 0)
        os.fchmod(descriptor, 0o700)
        for name in ('test.sh', 'verify.py', 'runtime_observer.py', 'provider.ts', 'context_observation.mjs'):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=descriptor)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise RuntimeError('Trusted asset must be a regular file: ' + name)
                os.fchown(fd, 0, 0)
                os.fchmod(fd, 0o600 if name.endswith(('.py', '.sh')) else 0o644)
                if name.endswith('.py'):
                    compile((directory / name).read_text(), str(directory / name), 'exec')
            finally:
                os.close(fd)
        os.fchmod(descriptor, 0o755)
    finally:
        os.close(descriptor)
except Exception as exc:
    # Only clean a directory whose identity and write boundary were established.
    if output_ready:
        for name in ('reward.txt', 'reward.json'):
            (output / name).unlink(missing_ok=True)
        (output / 'grading-status.json').write_text(json.dumps({
            'status': 'scoring_error', 'reason': str(exc),
            'scenario_inventory': [], 'completed_scenarios': [], 'command_exit_code': 2,
        }))
    print('Verifier preflight failed: ' + str(exc), flush=True)
    raise SystemExit(2)
PY
status=$?
if [ "$status" -ne 0 ]; then exit 2; fi
if [ "$status" -eq 0 ]; then
    python3 -I /tests/verify.py --repo /workspace/pi --output /logs/verifier/behavior
    status=$?
    if [ -f /logs/verifier/behavior/grading-status.json ]; then
        cp /logs/verifier/behavior/grading-status.json /logs/verifier/grading-status.json
    else
        status=2
        printf '{"status":"scoring_error","reason":"Verifier did not produce grading status","command_exit_code":2}\n' > /logs/verifier/grading-status.json
    fi
fi
# Harbor reads reward files independently of command exit status, and prefers
# JSON. Infrastructure failures must leave neither format behind.
if [ "$status" -eq 0 ] || [ "$status" -eq 1 ]; then
    reward=0
    if [ "$status" -eq 0 ]; then reward=1; fi
    printf '%s\n' "$reward" > /logs/verifier/reward.txt
    printf '{"reward":%s}\n' "$reward" > /logs/verifier/reward.json
else
    exit 2
fi
exit "$status"
