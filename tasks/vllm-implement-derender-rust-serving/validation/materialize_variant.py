"""Restore a complete variant inside a disposable qualification container."""
import os
from pathlib import Path
import subprocess
import sys

os.chdir("/workspace/vllm")
snapshot = {}
for path in Path("rust/src").rglob("*"):
    if path.is_file():
        stat = path.stat()
        snapshot[path] = (path.read_bytes(), stat.st_atime_ns, stat.st_mtime_ns)
subprocess.run(["git", "reset", "--hard", "e473e9036f979d546830aece9855027049faf0ba"], check=True)
subprocess.run(["git", "clean", "-fd", "rust/src"], check=True)
if len(sys.argv) > 1:
    subprocess.run(["git", "apply", "--check", sys.argv[1]], check=True)
    subprocess.run(["git", "apply", sys.argv[1]], check=True)
# Preserve Cargo freshness only for byte-identical sources. Changed sources
# keep their new timestamps; blindly restoring timestamps would reuse the
# wrong candidate, as documented in the task's original qualification.
for path, (content, atime, mtime) in snapshot.items():
    if path.is_file() and path.read_bytes() == content:
        os.utime(path, ns=(atime, mtime))
