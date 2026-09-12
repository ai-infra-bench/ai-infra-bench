from pathlib import Path
import subprocess,json,hashlib,concurrent.futures,time,sys
root=Path(__file__).parent;task=root/'task-snapshot';image='sha256:d11035d323cd8044e4a1aea97d0c3f7a03ae7865cadc84893bd045686da65eed'
candidate=Path('/data/pr54-codex-20260913/candidate-workspace')
def hashes():
 return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for directory in [task,candidate] for p in sorted(directory.rglob('*')) if p.is_file() and not p.is_symlink()}|{str(Path(__file__)):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
before=hashes();(root/'inputs-before.json').write_text(json.dumps({'image':image,'files':before},indent=2)+'\n')
cases=[('base',None,0),('oracle','solution/oracle.patch',1),('alternative','validation/sequential-probes-and-callable-alias.patch',1),('codex','validation/codex-session-only-cleanup.patch',0)]
def run(case):
 name,patch,expected=case;c='pr54-descendant-full-'+name;d=root/name;d.mkdir(exist_ok=True);t=time.monotonic()
 subprocess.run(['docker','run','-d','--name',c,'--network','none','--user','root','--cpus','4','--memory','16g','-v',str(task/'tests')+':/tests:ro','-v',str(task)+':/task:ro',image,'sleep','infinity'],check=True,stdout=subprocess.DEVNULL)
 try:
  if patch:subprocess.run(['docker','exec',c,'git','-C','/workspace/repo','-c','safe.directory=/workspace/repo','apply','/task/'+patch],check=True)
  if name=='codex':
   # The patch is a portable six-file source control. This run also overlays
   # the complete captured regular workspace, including ignored venv files.
   subprocess.run(['docker','cp',str(candidate)+'/.',c+':/workspace/repo/'],check=True)
  with (d/'test.log').open('w') as log:
   p=subprocess.run(['docker','exec',c,'timeout','900','bash','/tests/test.sh'],stdout=log,stderr=subprocess.STDOUT)
  reward=subprocess.check_output(['docker','exec',c,'cat','/logs/verifier/reward.txt'],text=True).strip()
  resources=json.loads(subprocess.check_output(['docker','exec',c,'python3','-c','import psutil,os,json; print(json.dumps({"processes":[(p.pid,p.name(),p.status()) for p in psutil.process_iter() if p.pid not in (1,os.getpid())],"listeners":[c.laddr.port for c in psutil.net_connections("tcp") if c.status=="LISTEN"]}))'],text=True))
  result={'case':name,'expected_reward':expected,'reward':reward,'shell_exit_code':p.returncode,'elapsed_s':round(time.monotonic()-t,2),'post_verifier_resources':resources,'scope':'Complete task 1.2.0 scoring script in pinned Docker image; no new model rollout.'}
  (d/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True);return result
 finally:subprocess.run(['docker','rm','-f',c],stdout=subprocess.DEVNULL)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(run,cases))
after=hashes();(root/'inputs-after.json').write_text(json.dumps({'image':image,'files':after,'unchanged':before==after},indent=2)+'\n')
(root/'results.json').write_text(json.dumps(results,indent=2)+'\n');assert before==after
assert all(x['reward']==str(x['expected_reward']) and not x['post_verifier_resources']['processes'] and not x['post_verifier_resources']['listeners'] for x in results)
