#!/usr/bin/env python3
"""Inspect a retained Docker image, including every saved historical layer."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

PRIVATE_MARKERS = [
    b'pi-safe-file-rollback', b'SafeRollbackStore', b'rollbackCheckpoint(',
    b'rollback_process_interruption', b'sdk_public_contract',
    b'Safe rollback after an interrupted coding task',
    b'PTRACE_GET_SYSCALL_INFO',
]
PRIVATE_NAMES = {
    'process_supervisor.py', 'sdk_peer.mjs', 'scripted_provider.py', 'tui_case.py',
    'safe-rollback.ts', 'alternative-blob-journal.patch', 'ci-cases.json',
}

INSPECT_FILESYSTEM = r'''
import collections,datetime,hashlib,json,os,pathlib,subprocess
root=pathlib.Path('/workspace/pi')
def git(*args):
 p=subprocess.run(['git','-c','safe.directory=/workspace/pi','-C',str(root),*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 return {'code':p.returncode,'stdout':p.stdout.strip(),'stderr':p.stderr.strip()}
r={'uid':os.getuid(),'gid':os.getgid(),'head':git('rev-parse','HEAD'),'status':git('status','--porcelain'),'remotes':git('remote','-v'),'refs':git('for-each-ref','--format=%(refname) %(objectname)'),'fsck':git('fsck','--full','--no-reflogs','--unreachable','--no-progress')}
obj=git('cat-file','--batch-all-objects','--batch-check=%(objectname) %(objecttype)')
objects={line.split()[0]:line.split()[1] for line in obj['stdout'].splitlines()}
reachable=git('rev-list','--objects','--all')
reachable_ids={line.split()[0] for line in reachable['stdout'].splitlines()}
r['git_objects']={'count':len(objects),'types':dict(collections.Counter(objects.values())),'unreachable_count':len(set(objects)-reachable_ids),'unreachable_sample':sorted(set(objects)-reachable_ids)[:10]}
log=git('log','--all','--format=%H %ct')
commits=[line.split() for line in log['stdout'].splitlines()]
cutoff=int(datetime.datetime.fromisoformat('2026-09-05T12:05:48+00:00').timestamp())
r['commit_dates']={'count':len(commits),'after_cutoff':[sha for sha,ts in commits if int(ts)>cutoff],'latest_epoch':max(int(ts) for sha,ts in commits)}
r['metadata']={p:(root/'.git'/p).exists() for p in ['FETCH_HEAD','ORIG_HEAD','logs','shallow','objects/info/alternates','info/grafts']}
private={'process_supervisor.py','sdk_peer.mjs','scripted_provider.py','tui_case.py','safe-rollback.ts','alternative-blob-journal.patch','ci-cases.json'}
hits=[];checkouts=[]
for where,dirs,files in os.walk('/',followlinks=False):
 if where=='/':dirs[:]=[x for x in dirs if x not in ('proc','sys','dev')]
 if '.git' in dirs:checkouts.append(str(pathlib.Path(where)/'.git'))
 for name in files:
  if name in private:hits.append(str(pathlib.Path(where)/name))
r['private_files']=hits;r['git_directories']=checkouts
r['private_root_directories']={p:pathlib.Path(p).exists() for p in ['/tests','/solution','/validation','/reproducer','/assets']}
r['package_lock_sha256']=hashlib.sha256((root/'package-lock.json').read_bytes()).hexdigest()
data=root/'packages/ai/src/providers/data'
r['model_data']={str(p.relative_to(data)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(data.rglob('*')) if p.is_file()}
r['npm_cache_present']=pathlib.Path('/root/.npm/_cacache').exists()
r['baseline_summary']=json.loads(pathlib.Path('/opt/pi-baseline/summary.json').read_text())
print(json.dumps(r))
'''

PERMISSIONS = r'''
import hashlib,json,os,pathlib,subprocess
r={'uid':os.getuid(),'gid':os.getgid(),'checks':{}}
base=pathlib.Path('/workspace/pi')
for rel in ['packages/coding-agent/src/core/session-manager.ts','packages/coding-agent/dist/index.js','node_modules/typescript/lib/typescript.js','package-lock.json']:
 p=base/rel
 r['checks'][rel]={'exists':p.exists(),'readable':os.access(p,os.R_OK),'writable':os.access(p,os.W_OK),'uid':p.stat().st_uid if p.exists() else None}
probe=base/'packages/coding-agent/src/.image-audit-probe'
try:probe.write_text('permission probe');probe.unlink();r['source_create_remove']=True
except OSError as e:r['source_create_remove']=str(e)
p=subprocess.run(['git','-C',str(base),'status','--porcelain'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
r['git_status']={'code':p.returncode,'stdout':p.stdout.strip(),'stderr':p.stderr.strip()}
p=subprocess.run(['node','packages/coding-agent/dist/cli.js','--version'],cwd=base,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
r['cli_version']={'code':p.returncode,'stdout':p.stdout.strip(),'stderr':p.stderr.strip()}
r['dependency_parent_rename_possible']=os.access(base,os.W_OK)
print(json.dumps(r))
'''


def run(command, **kwargs):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **kwargs)
    if result.returncode:
        raise RuntimeError({'command':command[:3], 'exit_code':result.returncode, 'stderr':result.stderr})
    return result.stdout


def scan_layers(image, extra_markers):
    process = subprocess.Popen(['docker','save',image],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    layers=[]
    with tarfile.open(fileobj=process.stdout,mode='r|') as archive:
        for member in archive:
            if not member.isfile() or not (member.name.endswith('/layer.tar') or member.name.startswith('blobs/')):
                continue
            found=[]; names=[]; count=0; scanned=0
            try:
                layer=tarfile.open(fileobj=archive.extractfile(member),mode='r|*')
            except tarfile.ReadError:
                # OCI config/manifest blobs are JSON, not filesystem layers.
                continue
            with layer:
                for entry in layer:
                    count+=1
                    clean=entry.name.lstrip('./')
                    if Path(clean).name in PRIVATE_NAMES or clean.split('/')[0] in ('tests','solution','validation','reproducer'):
                        names.append(clean)
                    if not entry.isfile():continue
                    stream=layer.extractfile(entry);suffix=b'';markers=set()
                    while True:
                        chunk=stream.read(1024*1024)
                        if not chunk:break
                        scanned+=len(chunk)
                        combined=suffix+chunk
                        markers.update(marker.decode() for marker in PRIVATE_MARKERS if marker in combined)
                        markers.update(f'private_input_{i}' for i,marker in enumerate(extra_markers) if marker in combined)
                        suffix=combined[-256:]
                    if markers:found.append({'path':clean,'markers':sorted(markers)})
            layers.append({'layer':member.name,'entries':count,'scanned_bytes':scanned,
                           'private_path_hits':names,'content_hits':found})
    code=process.wait()
    if code:raise RuntimeError(process.stderr.read().decode())
    return layers


def main():
    parser=argparse.ArgumentParser();parser.add_argument('image');parser.add_argument('--output',required=True)
    parser.add_argument('--private-marker', action='append', default=[], help='Additional private strings to detect; reported only by input index')
    args=parser.parse_args()
    inspect=json.loads(run(['docker','image','inspect',args.image]))[0]
    result={'image_id':inspect['Id'],'architecture':inspect['Architecture'],'size_bytes':inspect['Size'],
            'rootfs_layers':inspect['RootFS']['Layers'],'configured_user':inspect['Config'].get('User',''),
            'workdir':inspect['Config'].get('WorkingDir'),'labels':inspect['Config'].get('Labels'),
            'environment_names':sorted(x.split('=',1)[0] for x in inspect['Config'].get('Env',[]))}
    result['history']=[json.loads(x) for x in run(['docker','history','--no-trunc','--format','{{json .}}',args.image]).splitlines()]
    metadata=json.dumps({'inspect':inspect,'history':result['history']})
    result['private_metadata_input_hits']=[i for i,marker in enumerate(args.private_marker) if marker in metadata]
    result['filesystem']=json.loads(run(['docker','run','--rm','-i','--network','none','--entrypoint','python3',args.image,'-'],input=INSPECT_FILESYSTEM))
    result['node_user']=json.loads(run(['docker','run','--rm','-i','--network','none','--user','node','--entrypoint','python3',args.image,'-'],input=PERMISSIONS))
    result['historical_layer_scan']=scan_layers(args.image,[x.encode() for x in args.private_marker])
    Path(args.output).write_text(json.dumps(result,indent=2)+'\n')
    # docker save deduplicates repeated layer blobs (including empty layers).
    if len(result['historical_layer_scan']) != len(set(result['rootfs_layers'])):
        raise RuntimeError('Filesystem blob count does not match unique inspected RootFS layers')
    print(json.dumps({'image_id':result['image_id'],'layers':len(result['historical_layer_scan']),
                      'path_hits':sum(len(x['private_path_hits']) for x in result['historical_layer_scan']),
                      'content_hits':sum(len(x['content_hits']) for x in result['historical_layer_scan']),
                      'unreachable_objects':result['filesystem']['git_objects']['unreachable_count']}))


if __name__=='__main__':main()
