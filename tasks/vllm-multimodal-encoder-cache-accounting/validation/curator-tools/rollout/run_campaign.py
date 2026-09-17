"""A100 launcher. Source kernelgen/env.sh externally; never write its contents.
Prepare an immutable task snapshot with a pre-verifier collection hook. Mode
canary calls no model; mode flash executes exactly four parallel attempts.
"""
import argparse
import asyncio
import base64
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from urllib.parse import urlsplit
from harbor.job import Job
from harbor.models.job.config import JobConfig

HERE=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['canary','flash'])
    parser.add_argument('--task',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();source=args.task.resolve();output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    snapshot=output/'task';shutil.copytree(source,snapshot)
    collector=(HERE/'capture_final.py').read_bytes()
    command='python3 -I -S -c '+shlex.quote('import base64;exec(compile(base64.b64decode('+repr(base64.b64encode(collector).decode())+'),"<trusted-final-collector>","exec"))')
    with (snapshot/'task.toml').open('a') as f:
        f.write('\n[[verifier.collect]]\nuser = "root"\ntimeout_sec = 240\ncommand = '+json.dumps(command)+'\n')
    artifacts=[{'source':'/var/lib/pr84-final-capture','destination':'final-state'}]
    env={}
    model=None;hosts=[]
    if args.mode=='flash':
        model=os.environ.get('MODEL') or os.environ.get('ANTHROPIC_MODEL')
        assert model=='deepseek-v4-flash[1m]', 'unexpected flash model'
        assert os.environ.get('ANTHROPIC_AUTH_TOKEN') and os.environ.get('ANTHROPIC_BASE_URL')
        host=urlsplit(os.environ['ANTHROPIC_BASE_URL']).hostname;assert host
        hosts=[host]
        for key in ['ANTHROPIC_AUTH_TOKEN','ANTHROPIC_BASE_URL','ANTHROPIC_MODEL','CLAUDE_CODE_SUBAGENT_MODEL','ANTHROPIC_DEFAULT_SONNET_MODEL','ANTHROPIC_DEFAULT_OPUS_MODEL','ANTHROPIC_DEFAULT_HAIKU_MODEL']:
            if os.environ.get(key):env[key]='${'+key+'}'
    agent={'import_path':'campaign_agents:CollectionCanary' if args.mode=='canary' else 'campaign_agents:OfflineClaude',
           'model_name':model,'env':env,'extra_allowed_hosts':hosts,
           'kwargs':{'oracle_patch':str(snapshot/'solution/oracle.patch')} if args.mode=='canary' else {'version':'2.1.238'}}
    config={'job_name':args.mode,'jobs_dir':str(output/'jobs'),'n_attempts':1 if args.mode=='canary' else 4,
            'n_concurrent_trials':1 if args.mode=='canary' else 4,'quiet':True,
            'environment':{'type':'docker','delete':False,'kwargs':{'keep_containers':True}},'agents':[agent],
            'tasks':[{'path':str(snapshot)}],'artifacts':artifacts,'retry':{'max_retries':0}}
    (output/'job-config.json').write_text(json.dumps(config,indent=2)+'\n')
    inputs={str(p.relative_to(snapshot)):sha(p) for p in snapshot.rglob('*') if p.is_file()}
    manifest={'mode':args.mode,'model':model,'model_revision':'not supplied by endpoint',
              'reasoning_effort':'CLI/provider default; not overridden','harbor_version':importlib.metadata.version('harbor'),
              'cli_version':'2.1.238','cli_sha256':sha(Path('/usr/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe')),
              'task_source_commit':subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip(),
              'snapshot_sha256':inputs,'harness_sha256':{p.name:sha(p) for p in HERE.glob('*.py')},
              'agent_api_allowlist':hosts,'verifier_network':'task default no-network',
              'container_retention':'kept for outside-repository state inspection; cleanup after review'}
    (output/'experiment.json').write_text(json.dumps(manifest,indent=2)+'\n')
    job=await Job.create(JobConfig.model_validate(config))
    result=await job.run()
    (output/'job-result.json').write_text(result.model_dump_json(indent=2)+'\n')
    changed=[rel for rel,digest in inputs.items() if sha(snapshot/rel)!=digest]
    (output/'post-run-input-check.json').write_text(json.dumps({'changed':changed,'pass':not changed},indent=2)+'\n')
    assert not changed,changed
    print('CAMPAIGN_DONE',args.mode,str(output),flush=True)

if __name__=='__main__':asyncio.run(main())
