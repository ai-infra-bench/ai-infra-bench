"""Linux root smoke of /tests/test.sh with import-time attack controls.

Use only a disposable container. This checks transport, privilege isolation and
reward collection with a torch import stub; it is not a vLLM behavior run.
"""
from pathlib import Path
import json
import os
import subprocess
import sys

assert os.geteuid()==0
sys.path.insert(0,'/tests')
from completion_channel import execute_suite


def privilege_probe(inputs,checkpoint):
    import os
    assert os.geteuid()==65534
    checkpoint({'uid':os.geteuid()})


app=Path('/workspace/vllm');(app/'vllm').mkdir(parents=True,exist_ok=True)
app.chmod(0o755);(app/'vllm').chmod(0o755)
(app/'torch.py').write_text('# No torch operation is reached by import-time controls.\n')
positive=execute_suite(privilege_probe,{},candidate_path='/workspace/vllm')
assert json.loads(positive['payload'])=={'uid':65534},positive
results=[{'case':'honest-nobody-channel','pass':True}]
validation=Path(__file__).resolve().parents[1] / 'patches'
for name in ['dynamic-report-forgery','direct-completion-callback','early-os-exit','early-system-exit']:
    patch=(validation/(name+'.patch')).read_text()
    code='\n'.join(line[1:] for line in patch.splitlines() if line.startswith('+') and not line.startswith('+++'))
    (app/'vllm/__init__.py').write_text(code)
    run=subprocess.run(['bash','/tests/test.sh'],capture_output=True,text=True,timeout=90)
    reward=Path('/logs/verifier/reward.txt').read_text().strip()
    report=json.loads(Path('/logs/verifier/verification.json').read_text())
    expected='unauthenticated_completion' if name in ['dynamic-report-forgery','early-os-exit'] else 'worker_failed'
    assert run.returncode==0 and reward=='0' and report['reason']==expected,(name,run,report)
    if name=='dynamic-report-forgery':assert '---WORKER-PAYLOAD-BEGIN---' in report['diagnostic']
    if name=='direct-completion-callback':assert 'completion caller is not the trusted suite' in report['diagnostic']
    # Host collection compatibility: a non-root user can traverse/read both.
    access=subprocess.run(['runuser','-u','nobody','--','python3','-c',
        "from pathlib import Path; assert Path('/logs/verifier/reward.txt').read_text().strip()=='0'; Path('/logs/verifier/verification.json').read_text()"],capture_output=True)
    assert access.returncode==0,access.stderr
    results.append({'case':name,'reward':int(reward),'reason':report['reason'],'nobody_can_read_outputs':True})
print(json.dumps({'scope':'noncanonical Linux image; import-only torch stub; actual /tests/test.sh', 'results':results},indent=2))
