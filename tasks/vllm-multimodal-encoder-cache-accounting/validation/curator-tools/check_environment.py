import json
from pathlib import Path
import subprocess
import uuid
import argparse
import tomllib


def challenge_result(text, returncode):
    """Missing/malformed reports and setup errors are not negative evidence."""
    frames = [line.removeprefix('CHALLENGE_RESULT=') for line in text.splitlines()
              if line.startswith('CHALLENGE_RESULT=')]
    if len(frames) != 1:
        raise ValueError('challenge did not emit exactly one completed result')
    report = json.loads(frames[0])
    expected = {'pass': 0, 'behavior_mismatch': 1}
    if (not isinstance(report, dict) or report.get('status') not in expected
            or returncode != expected[report['status']]
            or report.get('stage') not in {'model_inputs', 'capacity_behavior',
                                           'video_capacity_behavior', 'storage_behavior'}):
        raise ValueError(f'challenge setup/execution failure: {report}')
    return report


def main():
    return run()


def run():
    parser=argparse.ArgumentParser()
    parser.add_argument('task',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--image')
    args=parser.parse_args()
    return check_environment(args.task.resolve(), args.output.resolve(), args.image)


def check_environment(task, out, override_image=None):
    out.mkdir(parents=True,exist_ok=True)
    image=override_image or tomllib.loads((task/'task.toml').read_text())['environment']['docker_image']
    name='pr84-env-'+uuid.uuid4().hex[:10]
    command=['docker','run','--name',name,'--network','none','--user','0:0','--cpus','4',
             '--memory','16g','--entrypoint','bash',
             '--mount',f'type=bind,source={task}/validation/challenge,target=/challenge,readonly',
             '--mount',f'type=bind,source={task}/tests,target=/tests,readonly',
             '--mount',f'type=bind,source={out},target=/evidence', image,'-c',SCRIPT]
    status={'scope':'agent imports, upstream test collection, and explicit Base challenge outcomes'}
    try:
        with (out/'environment.log').open('w') as log:
            result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=300)
        status['container_exit_code']=result.returncode
        if result.returncode:
            raise RuntimeError('environment setup did not complete')
        results={}
        for kind in ('cache','capacity'):
            exitcode=int((out/f'base-challenge-{kind}.exit').read_text())
            results[kind]=challenge_result((out/f'base-challenge-{kind}.log').read_text(), exitcode)
        status['challenges']=results
        # Window selection can already work on Base. The accounting challenge
        # must actually reach and reject its observed capacity behavior.
        if results['capacity']['status'] != 'behavior_mismatch':
            raise RuntimeError('Base accounting defect was not reproduced')
        status['exit_code']=0
    except Exception as exc:
        status.update(exit_code=1,error=repr(exc))
    finally:
        subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=20)
    (out/'status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(json.dumps(status,indent=2))
    return status['exit_code']


SCRIPT='''set -eu
runuser -u agent -- python3 -I -c 'import pathlib,torch,vllm; assert str(pathlib.Path(vllm.__file__).resolve()).startswith("/workspace/vllm/"); print("AGENT_IMPORT_OK", torch.__version__, vllm.__file__)'
runuser -u agent -- python3 -m pytest --collect-only -q tests/v1/core/test_encoder_cache_manager.py
set +e
runuser -u nobody -- python3 -I /challenge/challenge_encoder_cache.py > /evidence/base-challenge-cache.log 2>&1
printf '%s\\n' "$?" > /evidence/base-challenge-cache.exit
runuser -u nobody -- python3 -I /challenge/challenge_encoder_capacity.py > /evidence/base-challenge-capacity.log 2>&1
printf '%s\\n' "$?" > /evidence/base-challenge-capacity.exit
exit 0
'''


if __name__ == '__main__':
    raise SystemExit(main())
