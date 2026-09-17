"""Read-only audit of generated text/bytecode in a saved full repository.

Run after replay_saved.py has produced inventory.json. Uses a disposable,
network-disabled pristine container; never executes candidate bytecode.
"""
import argparse
import base64
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import uuid

p = argparse.ArgumentParser()
p.add_argument('--inventory', type=Path, required=True)
p.add_argument('--image', required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
a.output.mkdir(parents=True, exist_ok=False)
d = json.loads(a.inventory.read_text())
archive = Path(d['archive'])
with archive.open('rb') as f:
    assert hashlib.file_digest(f, 'sha256').hexdigest() == d['sha256']
paths = [k for k in d['changes'] if k.startswith(('.deps/', '.pytest_cache/', 'vllm/vllm_flash_attn/')) and not k.endswith('.so') and d['changes'][k]['after'] and d['changes'][k]['after']['type'] == 'file']
pairs = {k: k.split('/__pycache__/')[0] + '/' + k.split('/__pycache__/')[1].split('.cpython-')[0] + '.py' for k in d['changes'] if k.endswith('.pyc') and '-pytest-' not in k}
wanted = set(paths) | set(pairs) | set(pairs.values())
data = {}
with tarfile.open(archive, 'r|gz') as t:
    for m in t:
        name = m.name.removeprefix('repo/')
        if name in wanted and m.isfile():
            data[name] = t.extractfile(m).read()
for k in set(paths) | set(pairs):
    assert hashlib.sha256(data[k]).hexdigest() == d['changes'][k]['after']['sha256']
container = 'codex-pr70-generated-audit-' + uuid.uuid4().hex[:10]
subprocess.run(['docker', 'run', '-d', '--name', container, '--network', 'none', '--entrypoint', 'bash', a.image, '-lc', 'sleep infinity'], check=True, stdout=subprocess.DEVNULL)
try:
    code = '''
import base64,json,marshal,os,pathlib,platform,sys
v=json.load(sys.stdin); base={}; rows=[]
for p in v['paths']:
    f=pathlib.Path('/workspace/repo')/p
    if p.startswith('vllm/vllm_flash_attn/'):
        f=pathlib.Path(os.environ['VLLM_FLASH_ATTN_SRC_DIR'])/p.removeprefix('vllm/')
    base[p]=base64.b64encode(f.read_bytes()).decode() if f.is_file() else None
for p,s in v['pairs'].items():
    c=marshal.loads(base64.b64decode(v['data'][p])[16:])
    q=compile(base64.b64decode(v['data'][s]),c.co_filename,'exec',dont_inherit=True,optimize=0)
    rows.append(dict(path=p,matches_source_code=c==q))
print(json.dumps(dict(python=platform.python_version(),base=base,bytecode=rows)))
'''
    payload = dict(paths=paths, pairs=pairs, data={k: base64.b64encode(v).decode() for k, v in data.items()})
    result = json.loads(subprocess.check_output(['docker', 'exec', '-i', container, 'python3', '-c', code], input=json.dumps(payload).encode()))
finally:
    subprocess.run(['docker', 'rm', '-f', container], check=True, stdout=subprocess.DEVNULL)
diff = []
rows = {}
for k in paths:
    before = base64.b64decode(result['base'][k]) if result['base'][k] is not None else b''
    after = data[k]
    if d['changes'][k]['before'] is not None:
        assert hashlib.sha256(before).hexdigest() == d['changes'][k]['before']['sha256']
    rows[k] = dict(matches_pristine_text=before == after, after_sha256=hashlib.sha256(after).hexdigest())
    diff.extend(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True), fromfile='base/' + k, tofile='candidate/' + k))
(a.output / 'generated.diff').write_text(''.join(diff))
result.pop('base')
result.update(image=a.image, snapshot_sha256=d['sha256'], text=rows, pytest_rewritten_bytecode=[k for k in d['changes'] if k.endswith('.pyc') and '-pytest-' in k])
(a.output / 'record.json').write_text(json.dumps(result, indent=2))
print(json.dumps(dict(text_files=len(rows), ordinary_bytecode=len(result['bytecode']), bytecode_mismatches=[r for r in result['bytecode'] if not r['matches_source_code']])))
