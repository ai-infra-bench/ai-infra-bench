"""Run actual test.sh in disposable offline containers; not a Harbor run.
Usage: python run_matrix.py TASK_DIR OUTPUT_DIR [--image IMAGE] [--cases NAME...]
Default image must exist locally. Rebuilt images are explicitly noncanonical.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import uuid
import tomllib



def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--image')
    parser.add_argument('--cases',nargs='+')
    args=parser.parse_args()
    task=args.task.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    configured_image=tomllib.loads((task/'task.toml').read_text())['environment']['docker_image']
    args.image=args.image or configured_image
    inspect=subprocess.run(['docker','image','inspect',args.image],capture_output=True,text=True,timeout=30,check=True)
    (out/'image.json').write_text(inspect.stdout)
    image=json.loads(inspect.stdout)[0]
    cases=[{'name':'base','expected_reward':0,'apply_after':'base'}, {'name':'oracle','expected_reward':1,'apply_after':'oracle'}]
    cases+=json.loads((task/'validation/ci-cases.json').read_text())['cases']
    if args.cases:
        assert set(args.cases)<=set(c['name'] for c in cases)
        cases=[c for c in cases if c['name'] in args.cases]
    summary={'started_at':datetime.now(timezone.utc).isoformat(),'scope':'actual Docker test.sh; not Harbor','image_id':image['Id'],'canonical_image':image['Id']==configured_image,'artifacts':{},'cases':[]}
    for f in [task/'task.toml',*(task/'tests').rglob('*')]:
        if f.is_file():summary['artifacts'][str(f.relative_to(task))]=hashlib.sha256(f.read_bytes()).hexdigest()
    def save(): (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    save()
    for case in cases:
        name=case['name'];directory=out/name;directory.mkdir(exist_ok=False)
        cid='pr84-verify-'+uuid.uuid4().hex[:12]
        cmd=['docker','run','--name',cid,'--platform','linux/amd64','--network','none','--user','0:0','--cpus','4','--memory','16g','--entrypoint','bash']
        for source,target in [(task/'tests','/tests'),(task/'solution','/curator-solution'),(task/'validation','/curator-validation')]:
            cmd+=['--mount',f'type=bind,source={source},target={target},readonly']
        cmd+=['--mount',f'type=bind,source={directory},target=/logs/verifier',args.image,'-c',
              'set -eu\ncd /workspace/vllm\n'
              'test "$(runuser -u agent -- git rev-parse HEAD)" = 676db55eecf8b6d9ec38ea243cf6f35ea8378ec6\n'
              'command -v cc\npython3 -I -S -c "import sysconfig,pathlib; assert (pathlib.Path(sysconfig.get_path(\'include\'))/\'Python.h\').is_file()"\n'
              'if [ "$1" = oracle ]; then runuser -u agent -- git apply /curator-solution/oracle.patch; fi\n'
              'if [ -n "$2" ]; then runuser -u agent -- git apply "/curator-validation/$2"; fi\n'
              'bash /tests/test.sh\n'
              'if [ \"$3\" = challenge ]; then\n'
              'runuser -u nobody -- python3 -I /curator-validation/challenge/challenge_encoder_cache.py > /logs/verifier/challenge-cache.log 2>&1\n'
              'runuser -u nobody -- python3 -I /curator-validation/challenge/challenge_encoder_capacity.py > /logs/verifier/challenge-capacity.log 2>&1\n'
              'fi\n', 'matrix',case.get('apply_after','base'),case.get('patch',''),
              'challenge' if case['expected_reward']==1 else 'no-challenge']
        result={'name':name,'expected_reward':case['expected_reward']}
        print('RUN '+name,flush=True)
        try:
            with (directory/'container.log').open('w') as log:
                proc=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=720)
            result['exit_code']=proc.returncode
            reward=directory/'reward.txt'
            result['actual_reward']=int(reward.read_text().strip()) if reward.exists() else None
            result['matches_expected']=proc.returncode==0 and result['actual_reward']==case['expected_reward']
        except subprocess.TimeoutExpired:
            result['error']='container_timeout';result['matches_expected']=False
        finally:
            try: subprocess.run(['docker','rm','-f',cid],capture_output=True,timeout=20)
            except subprocess.TimeoutExpired: result['cleanup']='timeout; named container may remain: '+cid
        summary['cases'].append(result);save();print(json.dumps(result),flush=True)
        # Baseline/Oracle failures prevent interpreting later controls.
        if name in ('base','oracle') and not result['matches_expected']:break
    summary['finished_at']=datetime.now(timezone.utc).isoformat();save()

if __name__=='__main__':main()
