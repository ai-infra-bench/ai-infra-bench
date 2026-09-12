import subprocess,json,time,pathlib,concurrent.futures,sys
root=pathlib.Path('/tmp/ai-infra-pr54-hardening/tasks/vllm-dp-multi-port-supervisor');out=pathlib.Path('/data/pr54-hardening-20260913/matrix-final2');out.mkdir(exist_ok=True)
cases=[{'name':'base','expected_reward':0},{'name':'oracle','expected_reward':1}]+json.loads((root/'validation/ci-cases.json').read_text())['cases']
if len(sys.argv)>1:cases=[c for c in cases if c['name'] in sys.argv[1:]]
def run(case):
 name=case['name'];c='pr54-verified-'+name;d=out/name;d.mkdir(exist_ok=True);t=time.monotonic()
 subprocess.run(['docker','run','-d','--name',c,'--network','none','--user','root','--cpus','4','--memory','16g','-v',str(root/'tests')+':/tests:ro','-v',str(root)+':/task:ro','-v',str(d)+':/evidence','ai-infra-bench/vllm-dp-multi-port-supervisor:hardening-20260913-final','sleep','infinity'],check=True,stdout=subprocess.DEVNULL)
 try:
  if name!='base':
   patch='/task/solution/oracle.patch' if name=='oracle' else '/task/validation/'+case['patch']
   subprocess.run(['docker','exec',c,'git','-C','/workspace/repo','-c','safe.directory=/workspace/repo','apply',patch],check=True)
  with (d/'test.log').open('w') as log:
   p=subprocess.run(['docker','exec',c,'timeout','900','bash','/tests/test.sh'],stdout=log,stderr=subprocess.STDOUT)
  reward=subprocess.run(['docker','exec',c,'cat','/logs/verifier/reward.txt'],capture_output=True,text=True).stdout.strip()
  cleanup=subprocess.check_output(['docker','exec',c,'python3','-c','import psutil,os,json; print(json.dumps({"processes":[(p.pid,p.name(),p.status()) for p in psutil.process_iter() if p.pid not in (1,os.getpid())],"listeners":[c.laddr.port for c in psutil.net_connections("tcp") if c.status=="LISTEN"]}))'],text=True)
  r={'case':name,'expected':case['expected_reward'],'reward':reward,'exit':p.returncode,'elapsed_s':round(time.monotonic()-t,2),'post_test_resources':json.loads(cleanup)}
  (d/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
  return r
 finally: subprocess.run(['docker','stop','-t','3',c],stdout=subprocess.DEVNULL)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 results=list(pool.map(run,cases))
(out/'results.json').write_text(json.dumps(results,indent=2)+'\n')
