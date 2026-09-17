import json
from pathlib import Path
import subprocess
import uuid
import argparse
import tomllib
parser=argparse.ArgumentParser()
parser.add_argument('task',type=Path)
parser.add_argument('output',type=Path)
parser.add_argument('--image')
args=parser.parse_args()
task=args.task.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
image=args.image or tomllib.loads((task/'task.toml').read_text())['environment']['docker_image']
script='''set -eu
runuser -u agent -- python3 -I -c 'import pathlib,torch,vllm; assert str(pathlib.Path(vllm.__file__).resolve()).startswith("/workspace/vllm/"); print("AGENT_IMPORT_OK", torch.__version__, vllm.__file__)'
runuser -u agent -- python3 -m pytest --collect-only -q tests/v1/core/test_encoder_cache_manager.py
set +e
runuser -u nobody -- python3 -I /challenge/challenge_encoder_cache.py > /evidence/base-challenge-cache.log 2>&1
a=$?
runuser -u nobody -- python3 -I /challenge/challenge_encoder_capacity.py > /evidence/base-challenge-capacity.log 2>&1
b=$?
printf 'BASE_CHALLENGE_EXIT cache=%s capacity=%s\\n' "$a" "$b"
test "$a" -eq 1 && test "$b" -eq 1
'''
name='pr84-env-'+uuid.uuid4().hex[:10]
cmd=['docker','run','--name',name,'--network','none','--user','0:0','--cpus','4','--memory','16g','--entrypoint','bash','--mount',f'type=bind,source={task}/validation/challenge,target=/challenge,readonly','--mount',f'type=bind,source={out},target=/evidence',image,'-c',script]
try:
 with (out/'environment.log').open('w') as log:r=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=300)
 (out/'status.json').write_text(json.dumps({'exit_code':r.returncode,'scope':'pinned image agent imports, pytest collection, Base independent negative challenges'},indent=2))
finally:subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=20)
