"""Replay captured full repository states in fresh offline A100 containers.

Not a model rollout. Outside-repository mutations must be reviewed separately
before treating these repository-state replays as faithful delivered-state runs.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import time
import tomllib
import uuid


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


RESTORE = r'''
import hashlib,json,os,shutil,tarfile
from pathlib import Path
root=Path('/workspace/vllm')
manifest=json.loads(Path('/saved/manifest.json').read_text())
assert manifest['complete'] and not manifest['reward_existed']
for name,meta in manifest['artifacts'].items():
    assert hashlib.sha256((Path('/saved')/name).read_bytes()).hexdigest()==meta['sha256']
for path in root.iterdir():
    if path.name=='.git':continue
    if path.is_dir() and not path.is_symlink():shutil.rmtree(path)
    else:path.unlink()
with tarfile.open('/saved/final-tree.tar.gz') as archive:
    archive.extractall(root,filter='data')
for rel in manifest['omitted_pristine_native']:
    path=root/rel
    path.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(Path('/opt/vllm-native-overlay')/Path(rel).relative_to('vllm'),path)
for rel,meta in {**manifest['files'],**manifest['omitted_pristine_native']}.items():
    path=root/rel
    if meta['type']=='symlink':assert path.is_symlink() and os.readlink(path)==meta['target']
    else:
        assert hashlib.sha256(path.read_bytes()).hexdigest()==meta['sha256'],rel
        path.chmod(meta['mode'])
    os.chown(path,10001,10001,follow_symlinks=False)
print('SAVED_REPOSITORY_RESTORED_AND_HASH_VERIFIED')
'''

CHECK_STATE = r'''
import hashlib,json,os
from pathlib import Path
root=Path('/workspace/vllm')
manifest=json.loads(Path('/saved/manifest.json').read_text())
changed=[]
for rel,meta in manifest['files'].items():
    if '__pycache__' in Path(rel).parts:continue
    path=root/rel
    try:
        same=(path.is_symlink() and os.readlink(path)==meta['target']) if meta['type']=='symlink' else (not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest()==meta['sha256'])
    except OSError:same=False
    if not same:changed.append(rel)
print(json.dumps({'changed_existing_non_pyc_files':changed}))
raise SystemExit(bool(changed))
'''


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--campaign',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--task',type=Path,help='Freeze a revised grading task separately from original campaign inputs')
    parser.add_argument('--profile-probe',type=Path,help='Optional diagnostic script; never changes the reward')
    parser.add_argument('--probe-only',action='store_true',help='Run only the diagnostic on restored states')
    args=parser.parse_args()
    assert not args.probe_only or args.profile_probe
    campaign=args.campaign.resolve();output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    task=campaign/'task'
    if args.task:
        task=output/'grading-task'
        shutil.copytree(args.task.resolve(),task)
    probe=None
    if args.profile_probe:
        probe=output/'profile-probe.py'
        shutil.copy2(args.profile_probe.resolve(),probe)
    image=tomllib.loads((task/'task.toml').read_text())['environment']['docker_image']
    trials=sorted((campaign/'jobs/flash').glob('task__*'))
    assert len(trials)==4
    paths=[p for p in (task/'tests').rglob('*') if p.is_file()]
    paths += [p for p in (task/'validation/challenge').rglob('*') if p.is_file()]
    for trial in trials:
        paths += list((trial/'artifacts/final-state').glob('*'))
    paths.append(Path(__file__).resolve())
    if probe:paths.append(probe)
    hashes={str(p):sha(p) for p in paths if p.is_file()}
    (output/'pre-run.json').write_text(json.dumps(dict(image=image,started_at=time.time(),inputs=hashes,
        scope='fresh Docker test.sh and independent challenges on captured full repository state'),indent=2)+'\n')

    def replay(trial):
        out=output/trial.name;out.mkdir()
        container='pr84-replay-'+uuid.uuid4().hex[:12]
        result={'trial':trial.name,'started_at':time.time(),'commands':[]}
        def execute(name,command,timeout=660):
            started=time.time()
            with (out/(name+'.log')).open('w') as stream:
                proc=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
            result['commands'].append(dict(name=name,exit_code=proc.returncode,elapsed=time.time()-started))
            return proc.returncode
        try:
            command=['docker','run','-d','--name',container,'--network','none','--user','0:0',
                     '--cpus','4','--memory','16g','--entrypoint','sleep']
            for src,dst,readonly in [(trial/'artifacts/final-state','/saved',True),
                                      (task/'tests','/tests',True),
                                      (task/'validation/challenge','/challenge',True),
                                      (out,'/logs/verifier',False)]:
                command+=['--mount',f'type=bind,source={src},target={dst}'+(',readonly' if readonly else '')]
            command += [image,'infinity']
            assert execute('start',command,60)==0
            assert execute('restore',['docker','exec',container,'python3','-I','-S','-c',RESTORE],180)==0
            if not args.probe_only:
                execute('full-verifier',['docker','exec',container,'bash','/tests/test.sh'])
                for name in ('cache','capacity'):
                    execute('challenge-'+name,['docker','exec','-u','nobody',container,'python3','-I',
                        '/challenge/challenge_encoder_'+name+'.py'],300)
            if probe:
                assert execute('upload-profile-probe',['docker','cp',str(probe),container+':/tmp/profile-probe.py'],30)==0
                execute('profile-probe',['docker','exec','-u','nobody',container,'python3','-I',
                    '/tmp/profile-probe.py'],300)
            execute('post-state',['docker','exec',container,'python3','-I','-S','-c',CHECK_STATE],180)
            result['reward']=int((out/'reward.txt').read_text().strip()) if (out/'reward.txt').exists() else None
        except Exception as exc:
            result['error']=repr(exc)
        finally:
            subprocess.run(['docker','rm','-f',container],capture_output=True,timeout=30)
            result['finished_at']=time.time()
            (out/'replay.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result),flush=True)
        return result
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(replay,trials))
    changed=[name for name,digest in hashes.items() if sha(Path(name))!=digest]
    (output/'summary.json').write_text(json.dumps(dict(results=results,input_changes=changed),indent=2)+'\n')
    assert not changed


if __name__=='__main__':main()
