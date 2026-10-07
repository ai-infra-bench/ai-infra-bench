#!/bin/bash
set -euo pipefail
# Shared verification follows the agent phase. Stop its remaining processes and
# protect uploaded verifier files before importing any of them.
pkill -KILL -u agent || true
/usr/local/bin/python -I - <<'PROTECT'
import os
import stat
from pathlib import Path

root = Path('/tests')
paths = [root]
for parent, dirs, files in os.walk(root, followlinks=False):
    paths.extend(Path(parent) / name for name in dirs + files)
for path in paths:
    mode = path.lstat().st_mode
    if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
        raise RuntimeError(f'unsupported verifier upload entry: {path}')
    if stat.S_ISREG(mode) and path.stat().st_nlink != 1:
        raise RuntimeError(f'multiply-linked verifier upload: {path}')
for path in paths:
    os.chown(path, 0, 0, follow_symlinks=False)
    os.chmod(path, 0o700 if path.is_dir() else 0o600)
# Refuse links and protect existing output files before writing reward bytes.
for directory in (Path('/logs'), Path('/logs/verifier')):
    directory.mkdir(exist_ok=True)
    if not stat.S_ISDIR(directory.lstat().st_mode):
        raise RuntimeError(f'unsupported output directory: {directory}')
    os.chown(directory, 0, 0)
    os.chmod(directory, 0o755)
for path in Path('/logs/verifier').iterdir():
    mode = path.lstat()
    if not stat.S_ISREG(mode.st_mode) or mode.st_nlink != 1:
        raise RuntimeError(f'unsupported output entry: {path}')
    os.chown(path, 0, 0)
    os.chmod(path, 0o644)
PROTECT
umask 022
install -o root -g root -m 644 /tests/serve_candidate.py /opt/bridge-fixture.py
printf '0\n' > /logs/verifier/reward.txt
# Candidate source is never imported by this trusted parent interpreter.
/usr/local/bin/python -I /tests/prepare.py
exec /usr/local/bin/python -I /tests/grade.py --repo /workspace/Gym --python /usr/local/bin/python \
  --fixture /opt/bridge-fixture.py --candidate-user agent --output /logs/verifier
