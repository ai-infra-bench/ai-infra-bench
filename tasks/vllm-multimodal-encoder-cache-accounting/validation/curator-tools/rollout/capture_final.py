"""Trusted pre-verifier collector, invoked with python3 -I -S as root."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tarfile
import time

ROOT=Path('/workspace/vllm')
OUT=Path('/var/lib/pr84-final-capture')
BASE='676db55eecf8b6d9ec38ea243cf6f35ea8378ec6'
assert not OUT.exists(), 'collector output already exists'
OUT.mkdir(mode=0o700)

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def git(*args):
    command=['runuser','-u','agent','--','git','-c','core.fsmonitor=false','-c','core.hooksPath=/dev/null','-C',str(ROOT),*args]
    result=subprocess.run(command,capture_output=True,timeout=120)
    if result.returncode:raise RuntimeError('git capture failed: '+repr(args)+' '+result.stderr.decode(errors='replace'))
    return result.stdout

manifest={'schema':'pr84.final-state.v1','started_at':time.time(),'base':BASE,
          'repository':str(ROOT),'phase':'after_agent_before_verifier',
          'reward_existed':Path('/logs/verifier/reward.txt').exists(),
          'files':{},'omitted_pristine_native':{},'unsupported':[]}
(OUT/'tracked.patch').write_bytes(git('diff','--binary','--no-ext-diff','--no-textconv',BASE,'--'))
(OUT/'status.z').write_bytes(git('status','--porcelain=v1','-z','--untracked-files=all'))
(OUT/'head.txt').write_bytes(git('rev-parse','HEAD'))
(OUT/'git-log.txt').write_bytes(git('log','-8','--format=%H %s'))
untracked=set(git('ls-files','--others','--exclude-standard','-z').decode().split('\0'))-{''}
manifest['untracked_paths']=sorted(untracked)
with tarfile.open(OUT/'final-tree.tar.gz','w:gz',dereference=False) as archive, tarfile.open(OUT/'untracked.tar.gz','w:gz',dereference=False) as extra:
    for current,dirs,names in os.walk(ROOT,followlinks=False):
        if Path(current)==ROOT:dirs[:]=[d for d in dirs if d!='.git']
        # Include directory symlinks themselves without traversing them.
        entries=names+[d for d in dirs if (Path(current)/d).is_symlink()]
        for name in sorted(entries):
            path=Path(current)/name;rel=path.relative_to(ROOT).as_posix();metadata=path.lstat()
            if stat.S_ISLNK(metadata.st_mode):record={'type':'symlink','target':os.readlink(path),'mode':stat.S_IMODE(metadata.st_mode)}
            elif stat.S_ISREG(metadata.st_mode):record={'type':'file','sha256':digest(path),'size':metadata.st_size,'mode':stat.S_IMODE(metadata.st_mode)}
            else:manifest['unsupported'].append(rel);continue
            native=Path('/opt/vllm-native-overlay')/Path(rel).relative_to('vllm') if rel.startswith('vllm/') else None
            if record['type']=='file' and native and native.is_file() and not native.is_symlink() and record['sha256']==digest(native):
                manifest['omitted_pristine_native'][rel]=record;continue
            manifest['files'][rel]=record
            archive.add(path,arcname=rel,recursive=False)
            if rel in untracked:extra.add(path,arcname=rel,recursive=False)
# Detect changes during collection rather than silently certifying a moving tree.
manifest['unstable']=[]
for rel,record in manifest['files'].items():
    path=ROOT/rel
    try:
        stable=(path.is_symlink() and os.readlink(path)==record['target']) if record['type']=='symlink' else (not path.is_symlink() and digest(path)==record['sha256'])
    except OSError:stable=False
    if not stable:manifest['unstable'].append(rel)
manifest['complete']=not manifest['unsupported'] and not manifest['unstable']
manifest['artifacts']={p.name:{'sha256':digest(p),'size':p.stat().st_size} for p in OUT.iterdir() if p.is_file()}
manifest['finished_at']=time.time()
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
assert manifest['complete'], 'unstable or unsupported final files'
print('FINAL_STATE_CAPTURED',len(manifest['files']),len(untracked))
