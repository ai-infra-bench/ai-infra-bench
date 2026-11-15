"""Fault-injection controls over fresh real responses; not new model evaluations."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import subprocess,json,copy,os,sys,argparse
task=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--responses',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--code-image',required=True)
args=parser.parse_args()
root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
original=json.loads(args.responses.read_text())
assert original['new_model_run'] and original['total']==100
env=dict(os.environ);env['PATH']=str(Path(sys.executable).parent)+':'+env['PATH'];env.pop('PYTHONPATH',None)
def run(name):
 report=copy.deepcopy(original)
 rows={x['id']:x for x in report['results']}
 expected=None
 if name=='wrong-code':rows['C31']['output']='def has_close_elements(numbers, threshold):\n    return None';expected=('C31','WRONG_RESULT')
 elif name=='wrong-math':rows['M31']['output']='FINAL_ANSWER: -999999';expected=('M31','WRONG_RESULT')
 elif name=='wrong-instruction':rows['I22']['output']='HELLO';expected=('I22','INSTRUCTION_FAILURE')
 elif name=='truncated':rows['C01']['metadata']['finish_reason']={'type':'length'};expected=('C01','TRUNCATED')
 elif name=='over-budget':rows['M31']['metadata']['completion_tokens']=1025;expected=('M31','OUTPUT_BUDGET_EXCEEDED')
 elif name=='test-mutation':
  rows['C31']['output']="import inspect\np=inspect.currentframe().f_back.f_globals\np['data']['tests']=['pass']*len(p['data']['tests'])\ndef has_close_elements(numbers,threshold):return None"
  expected=('C31','CODE_RUNTIME_ERROR')
 elif name=='system-exit':rows['C31']['output']='raise SystemExit(0)';expected=('C31','CODE_RUNTIME_ERROR')
 elif name=='process-exit':rows['C31']['output']='import os; os._exit(0)';expected=('C31','CODE_RUNTIME_ERROR')
 elif name=='missing-case':report['results'].pop()
 elif name=='duplicate-case':report['results'].append(copy.deepcopy(report['results'][0]))
 elif name=='wrong-suite-hash':report['suite_sha256']='0'*64
 else:raise ValueError(name)
 out=root/name;collection=out/'collection';(collection/'quality').mkdir(parents=True,exist_ok=False)
 # Deliberately minimal fixture: rejected quality must stop before any throughput score.
 (collection/'collection.json').write_text(json.dumps({'status':'COLLECTED','mode':'full','fixture':True}))
 (collection/'quality/responses.json').write_text(json.dumps(report))
 cmd=['bash',str(task/'tests/test.sh'),'--collection',str(collection),'--output',str(out/'graded'),'--code-image',args.code_image]
 p=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=240)
 (out/'command.log').write_text(p.stdout+p.stderr)
 record=json.loads((out/'graded/summary.json').read_text());assert p.returncode!=0 and record['valid'] is False and record['score'] == 0.0,(name,p.returncode,record['score'])
 assert float((out/'graded/reward.txt').read_text())==0.0
 if expected:
  s=json.loads((out/'graded/quality/summary.json').read_text());failed=[(v['id'],v['status']) for v in s['results'] if not v['passed']]
  assert s['status']=='FAILED' and s['passed']==99 and expected in failed,(name,s['status'],failed)
 else:
  message={'missing-case':'Responses must cover every case exactly once','duplicate-case':'Duplicate response IDs','wrong-suite-hash':'Response suite digest mismatch'}[name]
  assert message in p.stderr,(name,p.stderr[-500:])
 return {'control':name,'exit_code':p.returncode,'score':record['score'],'valid':record['valid'],'rejected_for_expected_reason':True}
with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,['wrong-code','wrong-math','wrong-instruction','truncated','over-budget','test-mutation','system-exit','process-exit','missing-case','duplicate-case','wrong-suite-hash']))
value={'scope':'Host test.sh fault-injection controls using fresh real responses; not additional native model runs.','controls':results}
(root/'summary.json').write_text(json.dumps(value,indent=2));print(json.dumps(value))
