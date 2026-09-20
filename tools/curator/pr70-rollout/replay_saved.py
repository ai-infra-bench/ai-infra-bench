"""Curator replay of a complete pre-verifier repository snapshot (not a model run)."""
import argparse, hashlib, json, subprocess, tarfile, time
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--container', required=True)
p.add_argument('--snapshot', type=Path, required=True)
p.add_argument('--base-manifest', type=Path, required=True)
p.add_argument('--task', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=False)
def sha(f):
    with Path(f).open('rb') as s:
        return hashlib.file_digest(s, 'sha256').hexdigest()
def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)
def shell(cmd):
    return run(['docker', 'exec', '-u', 'root', a.container, 'bash', '-lc', cmd])
def cp(src, dest):
    return run(['docker', 'cp', str(src), a.container + ':' + dest])
archive = a.snapshot / 'full-repository.tar.gz'
manifest = json.loads((a.snapshot / 'manifest.json').read_text())
for name, info in manifest['files'].items():
    assert sha(a.snapshot / name) == info['sha256'], name
files = {}
with tarfile.open(archive, 'r|gz') as t:
    for m in t:
        parts = Path(m.name).parts
        if parts and parts[0] == 'repo':
            parts = parts[1:]
        if not parts or parts[0] == '.git':
            continue
        name = '/'.join(parts)
        if m.isfile():
            files[name] = dict(bytes=m.size, sha256=hashlib.file_digest(t.extractfile(m), 'sha256').hexdigest(), type='file')
        elif m.issym():
            files[name] = dict(type='symlink', target=m.linkname)
base = json.loads(a.base_manifest.read_text())
changes = {k: dict(before=base.get(k), after=files.get(k)) for k in sorted(set(base) | set(files)) if base.get(k) != files.get(k)}
(a.output/'inventory.json').write_text(json.dumps(dict(archive=str(archive), sha256=sha(archive), changes=changes), indent=2))
frozen = {str(f): sha(f) for f in a.task.rglob('*') if f.is_file()}
record = dict(started=time.time(), snapshot=str(a.snapshot), snapshot_manifest=manifest, task_hashes=frozen, probes=[], kind='saved-full-repository-replay', outside_repository='Reviewed trajectory; full root filesystem not captured')
(a.output/'pre-run.json').write_text(json.dumps(record, indent=2))
cp(archive, '/tmp/saved-repository.tar.gz')
shell('rm -rf /workspace/repo && tar -xzf /tmp/saved-repository.tar.gz -C /workspace && chown -R agent:agent /workspace/repo && mkdir -p /tests /validation /logs/verifier')
cp(str(a.task/'tests')+'/.', '/tests')
cp(str(a.task/'validation')+'/.', '/validation')
# Existing task rebuild remains authoritative; no delivered shared library is substituted.
with (a.output/'entrypoint.log').open('w') as log:
    r = subprocess.run(['docker','exec','-u','root',a.container,'bash','/tests/test.sh'], stdout=log, stderr=subprocess.STDOUT, timeout=3600)
record['entrypoint_exit'] = r.returncode
run(['docker','cp',a.container+':/logs/verifier',str(a.output/'verifier')])
record['reward'] = float((a.output/'verifier/reward.txt').read_text())
record['rebuilt_native_sha256'] = subprocess.check_output(['docker','exec',a.container,'sha256sum','/workspace/repo/vllm/_C.abi3.so'],text=True).split()[0]
for dtype in ('float16','bfloat16','float32'):
    for offset in (0,1,3):
        for mode in ('public','native'):
            label=f'offset-{dtype}-{offset}-{mode}'
            with (a.output/(label+'.log')).open('w') as log:
                r=subprocess.run(['docker','exec','-u','agent',a.container,'python3','-I','/validation/challenge/offset_input_probe.py','--dtype',dtype,'--offset',str(offset),'--mode',mode],stdout=log,stderr=subprocess.STDOUT,timeout=120)
            record['probes'].append(dict(name=label,exit_code=r.returncode))
# Isolate each existing contract case, so an earlier asynchronous CUDA error cannot hide its source.
code='''
import sys,json
sys.path.insert(0,'/tests')
from quant_boundary import cases,observe,compare,frozen_observations
from vllm.model_executor.layers.quantization.utils.int8_utils import per_token_group_quant_int8
c=next(c for c in cases() if c['name']==sys.argv[1])
print('CASE='+json.dumps(c),flush=True)
# Run the frozen reference in a separate process before the candidate can
# leave a pending CUDA error. A successful observation alone is not a pass:
# invalid launches can return unwritten output without raising immediately.
expected=frozen_observations([c],'/tests/frozen-reference')
r=observe([c],per_token_group_quant_int8)
print('OBSERVED='+json.dumps(r),flush=True)
errors=compare(r,expected)
print('COMPARISON='+json.dumps(dict(errors=errors)),flush=True)
raise SystemExit(bool(errors))
'''
for name in ('single-large-fp32','single-large-fp16','unaligned-fp16','unaligned-bf16','unaligned-fp32'):
    with (a.output/('isolated-'+name+'.log')).open('w') as log:
        r=subprocess.run(['docker','exec','-u','agent',a.container,'python3','-I','-c',code,name],stdout=log,stderr=subprocess.STDOUT,timeout=120)
    record['probes'].append(dict(name=name,exit_code=r.returncode))
record['finished']=time.time()
record['inputs_unchanged']=frozen=={str(f):sha(f) for f in a.task.rglob('*') if f.is_file()} and sha(archive)==manifest['files']['full-repository.tar.gz']['sha256']
(a.output/'record.json').write_text(json.dumps(record,indent=2))
assert record['inputs_unchanged']
print(json.dumps(dict(reward=record['reward'],probes=record['probes'])),flush=True)
