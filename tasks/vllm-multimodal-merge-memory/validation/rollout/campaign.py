"""Four concurrent fixed-GPU Harbor attempts; credentials stay in host env."""
import argparse,concurrent.futures,hashlib,json,os,shutil,subprocess,time
from pathlib import Path
import yaml
from urllib.parse import urlsplit
p=argparse.ArgumentParser();p.add_argument('--round',required=True);p.add_argument('--mode',choices=['smoke','flash'],required=True);p.add_argument('--root',type=Path,required=True);a=p.parse_args()
TASK=Path(__file__).resolve().parents[2];R=a.root/a.round;R.mkdir(parents=True,exist_ok=False)
HARBOR='/tmp/codex-pr63-hardening-20260918/harbor-venv/bin/harbor'
os.environ['DOCKER_CONFIG']='/tmp/codex-pr63-hardening-20260918/docker-config'
os.environ['LITELLM_LOCAL_MODEL_COST_MAP']='True'
os.environ['PYTHONDONTWRITEBYTECODE']='1'
os.environ['PR63_CLAUDE_BINARY']='/usr/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe'
os.environ['PYTHONPATH']=str(Path(__file__).parent)
model=os.environ.get('MODEL') if a.mode=='flash' else None
if a.mode=='flash':assert model=='deepseek-v4-flash[1m]', 'unexpected configured model'
def hashes(root):return {str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in root.rglob('*') if f.is_file()}
commit=subprocess.check_output(['git','-C',str(TASK),'rev-parse','HEAD'],text=True).strip()
meta={'commit':commit,'mode':a.mode,'model':model,'model_revision':'not provided by gateway','harbor':'0.22.0','claude_code':'2.1.238','reasoning_effort':'CLI/provider default (no override)','concurrency':4 if a.mode=='flash' else 1,'task_hashes':hashes(TASK),'started_unix':time.time(),'trials':[]}
(R/'campaign.json').write_text(json.dumps(meta,indent=2)+'\n')
def run(slot):
 name=f'{a.round}-gpu{slot}';prepared=R/'inputs'/name;shutil.copytree(TASK,prepared)
 for file in ['environment/docker-compose.yaml','tests/docker-compose.yaml']:
  q=prepared/file;d=yaml.safe_load(q.read_text());device=d['services']['main']['deploy']['resources']['reservations']['devices'][0];device.pop('count',None);device['device_ids']=[str(slot)];q.write_text(yaml.safe_dump(d,sort_keys=False))
 frozen=hashes(prepared)
 (R/f'{name}-inputs.json').write_text(json.dumps(frozen,indent=2)+'\n')
 agent='capture_agent:CapturedClaude' if a.mode=='flash' else 'capture_agent:CaptureSmoke'
 cmd=[HARBOR,'run','-p',str(prepared),'-a',agent,'--override-gpus','0','--jobs-dir',str(R/'jobs'),'--job-name',name,'--n-concurrent','1','--max-retries','0']
 if not model:cmd+=['--ak','task_dir='+str(prepared)]
 if model:cmd+=['--allow-agent-host',urlsplit(os.environ['ANTHROPIC_BASE_URL']).hostname,'-m',model,'--ak','version=2.1.238','--ae','DISABLE_AUTOUPDATER=1']
 start=time.time()
 with (R/f'{name}-launcher.log').open('w') as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
 rows=[]
 for f in (R/'jobs'/name).glob('*/result.json'):
  d=json.loads(f.read_text());rows.append({'result_path':str(f),'trial_id':d.get('id'),'reward':(d.get('verifier_result') or {}).get('rewards'),'exception':d.get('exception_info'),'task_checksum':d.get('task_checksum')})
 record={'slot':slot,'command':cmd,'exit_code':r.returncode,'seconds':round(time.time()-start,3),'results':rows,'inputs_unchanged':frozen==hashes(prepared)}
 (R/f'{name}-summary.json').write_text(json.dumps(record,indent=2)+'\n')
 print(json.dumps(record),flush=True)
 return record
with concurrent.futures.ThreadPoolExecutor(max_workers=meta['concurrency']) as pool:meta['trials']=list(pool.map(run,range(meta['concurrency'])))
meta['finished_unix']=time.time();meta['canonical_inputs_unchanged']=meta['task_hashes']==hashes(TASK)
(R/'campaign.json').write_text(json.dumps(meta,indent=2)+'\n')
assert meta['canonical_inputs_unchanged'] and all(x['inputs_unchanged'] for x in meta['trials'])
