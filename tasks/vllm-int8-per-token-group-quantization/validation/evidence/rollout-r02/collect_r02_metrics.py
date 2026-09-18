from pathlib import Path
from datetime import datetime
import json,tarfile,hashlib,sys
r=Path(sys.argv[1]);out=Path(sys.argv[2]);result={'round':'flash-r02','review_revision':'08c99c4e3f8e5120ed0ebbffd689e2be366bf5f0','trials':[]}
def elapsed(x):return (datetime.fromisoformat(x['finished_at'].replace('Z','+00:00'))-datetime.fromisoformat(x['started_at'].replace('Z','+00:00'))).total_seconds()
for g in (4,5,6,7):
 t=next((r/'jobs'/f'flash-r02-gpu{g}').glob('flash-r02-gpu*'));p=t/'result.json'
 if not p.exists():continue
 d=json.loads(p.read_text());a=json.loads((t/'agent/trajectory.json').read_text());f=t/'agent/final-state';m=json.loads((f/'manifest.json').read_text());fs={};cur=None
 for l in (f/'tracked.patch').read_text().splitlines():
  if l.startswith('diff --git '):cur=l.split(' b/',1)[1];fs[cur]={'added':0,'removed':0}
  elif cur and l.startswith('+') and not l.startswith('+++'):fs[cur]['added']+=1
  elif cur and l.startswith('-') and not l.startswith('---'):fs[cur]['removed']+=1
 with tarfile.open(f/'untracked.tar.gz') as ar:
  for member in ar:
   if member.isfile():
    data=ar.extractfile(member).read();fs[member.name]={'added':len(data.decode().splitlines()),'removed':0,'sha256':hashlib.sha256(data).hexdigest()}
 log=t/'verifier/verification.log';v=json.loads(log.read_text().split('\n',1)[1]);raw=next((t/'agent/sessions/projects/-workspace-repo').glob('*.jsonl'))
 item={'gpu':g,'id':d['id'],'trial_name':d['trial_name'],'task_checksum':d['task_checksum'],'original_reward':d['verifier_result']['rewards']['reward'],'exception_info':d['exception_info'],'seconds':{'total':elapsed(d),'agent':elapsed(d['agent_execution']),'verifier':elapsed(d['verifier'])},'atif_steps':len(a['steps']),'agent_steps':sum(s['source']=='agent' for s in a['steps']),'top_level_tool_calls':sum(len(s.get('tool_calls') or []) for s in a['steps']),'source_files':fs,'source_totals':{'files':len(fs),'added':sum(x['added'] for x in fs.values()),'removed':sum(x['removed'] for x in fs.values())},'raw_final_boundary':len(raw.read_text().splitlines()),'snapshot':m['files']['full-repository.tar.gz'],'formal_verification':v}
 replay=Path('work/rollout70/replays-r02')/f'replay-r02-gpu{g}'/'record.json'
 if replay.exists():
  q=json.loads(replay.read_text());item['full_saved_replay']={k:q[k] for k in ('reward','probes','inputs_unchanged','rebuilt_native_sha256','started','finished')}
 result['trials'].append(item)
out.write_text(json.dumps(result,indent=2)+'\n');print([(x['gpu'],x['original_reward'],x['source_totals'],x['seconds']) for x in result['trials']])
