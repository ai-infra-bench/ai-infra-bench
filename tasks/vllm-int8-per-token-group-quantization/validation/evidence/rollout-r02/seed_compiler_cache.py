"""Curator-only ccache seed, strictly after Harbor enters verification.

No library injection or build-directory reuse. Ccache validates source, included
headers and compiler flags before returning an object. Add complete immutable
cache entries atomically; never overwrite a concurrently written entry.
"""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time

container, output = sys.argv[1:3]
root = Path(__file__).parent
source = root / "compiler-ccache-v1-full"
subprocess.run(["docker", "exec", container, "bash", "-lc",
                "test -s /logs/verifier/native-build.stdout.log && "
                "test -f /logs/verifier/frozen-reference-stage.txt"], check=True)
provenance = subprocess.check_output(["docker", "exec", container, "cat",
                                     "/logs/verifier/candidate-provenance.txt"], text=True)
target = "/opt/bench/verifier-ccache-seed"
subprocess.run(["docker", "cp", str(source) + "/.", container + ":" + target], check=True)
code = """
from pathlib import Path
import os,json
src=Path('/opt/bench/verifier-ccache-seed')
dst=Path('/home/agent/.cache/ccache')
added=existing=0
for path in src.rglob('*'):
    if not path.is_file() or not path.name.endswith(('R','M')): continue
    target=dst/path.relative_to(src)
    target.parent.mkdir(parents=True,exist_ok=True)
    for parent in (target.parent,target.parent.parent,dst):
        os.chown(parent,1000,1000)
    try:
        os.link(path,target)
        os.chown(target,1000,1000)
        added+=1
    except FileExistsError:
        existing+=1
print(json.dumps({'added':added,'existing':existing}))
"""
result = subprocess.check_output(["docker", "exec", "-u", "root", container, "python3", "-c", code], text=True)
record = dict(phase="verifier_only_after_agent_completion", container=container,
              timestamp=time.time(), candidate_provenance=provenance,
              cache_entries={str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in source.rglob("*") if p.is_file() and p.name.endswith(("R", "M"))},
              result=json.loads(result), source="compiler outputs from documented development and superseded first-matrix builds",
              native_library_injected=False, build_directory_injected=False)
Path(output).write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record["result"]))
