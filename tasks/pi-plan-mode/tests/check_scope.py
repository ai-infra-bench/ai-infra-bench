#!/usr/bin/env python3
"""Read-only check that candidate edits stay within the public task scope."""
import hashlib
import json
import sys
import subprocess
from pathlib import Path

root = Path(sys.argv[1]); manifest = json.loads((Path(__file__).parent / "base-manifest.json").read_text())
problems = []
for name, digest in manifest["frozen"].items():
    path = root / name
    content = str(path.readlink()).encode() if path.is_symlink() else path.read_bytes() if path.is_file() else None
    # Relevant utility tests may be extended; grading restores the pinned Base copy.
    if name == "packages/coding-agent/test/plan-mode-utils.test.ts" and path.is_file() and not path.is_symlink():
        continue
    # Base .gitattributes deliberately checks Windows scripts out as CRLF;
    # Git blobs and archive-based Linux checkouts may contain LF.
    if content is not None and path.suffix in {".bat", ".cmd", ".ps1"}: content = content.replace(b"\r\n", b"\n")
    if content is None or hashlib.sha256(content).hexdigest() != digest: problems.append(name)
report = {"passed": not problems, "changed_frozen_files": problems}
allowed_roots = [root / "packages/coding-agent/examples/extensions/plan-mode", root / "packages/coding-agent/test"]
new_problems = []
try:
    untracked = subprocess.check_output(["git", "-C", str(root), "ls-files", "--others", "--exclude-standard", "-z"]).decode().split("\0")
    for name in filter(None, untracked):
        path = root / name
        if not any(path.is_relative_to(allowed) for allowed in allowed_roots): new_problems.append(name)
        elif path.is_symlink() and not any(path.resolve().is_relative_to(allowed.resolve()) for allowed in allowed_roots): new_problems.append(name + " (symlink escapes allowed scope)")
except (OSError, UnicodeDecodeError, subprocess.CalledProcessError) as error:
    new_problems.append("could not inventory added files: " + str(error))
report.update(passed=not (problems or new_problems), added_outside_scope=new_problems)
print(json.dumps(report)); raise SystemExit(0 if report["passed"] else 1)
