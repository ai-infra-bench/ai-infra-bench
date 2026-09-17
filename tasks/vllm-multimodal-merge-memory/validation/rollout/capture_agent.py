"""Campaign-only Harbor agents: stock Claude behavior plus pre-verifier capture."""
import hashlib
import json
import os
from pathlib import Path
import shlex

from harbor.agents.installed.claude_code import ClaudeCode
from harbor.agents.base import BaseAgent

COLLECT = r'''
from pathlib import Path
import hashlib,json,os,subprocess,tarfile,time
r=Path('/workspace/repo');o=Path('/tmp/pr63-final-capture');o.mkdir(mode=0o700,exist_ok=False)
def git(*a):
 p=subprocess.run(['git','-c','safe.directory='+str(r),*a],cwd=r,capture_output=True)
 if p.returncode:raise RuntimeError(p.stderr.decode(errors='replace'))
 return p.stdout
(o/'tracked.patch').write_bytes(git('diff','--binary','36d7f19897843c9cbdb701ba88d0f2c29954fe44','--'))
(o/'status.txt').write_bytes(git('status','--porcelain=v1','--untracked-files=all'))
(o/'git-history.txt').write_bytes(git('log','-8','--format=%H %s'))
(o/'untracked-paths.bin').write_bytes(git('ls-files','--others','--exclude-standard','-z'))
paths=[os.fsdecode(x) for x in (o/'untracked-paths.bin').read_bytes().split(b'\0') if x]
with tarfile.open(o/'untracked.tar.gz','w:gz',compresslevel=1,dereference=False) as t:
 for p in paths:t.add(r/p,arcname=p,recursive=False)
with tarfile.open(o/'full-repository.tar.gz','w:gz',compresslevel=1,dereference=False) as t:t.add(r,arcname='repo')
manifest={}
for p in sorted(o.iterdir()):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 manifest[p.name]={'bytes':p.stat().st_size,'sha256':h.hexdigest()}
(o/'manifest.json').write_text(json.dumps({'captured_at_unix':time.time(),'phase':'after agent run, before verifier','base':'36d7f19897843c9cbdb701ba88d0f2c29954fe44','head':git('rev-parse','HEAD').decode().strip(),'files':manifest},indent=2)+'\n')
'''

class CaptureMixin:
    async def run(self, instruction, environment, context):
        try:
            await super().run(instruction, environment, context)
        finally:
            result = await environment.exec(command='python3 -I -c '+shlex.quote(COLLECT),user='root',timeout_sec=900)
            if result.return_code != 0:
                raise RuntimeError('pre-verifier collection failed: '+str(result.stderr))
            await environment.download_dir('/tmp/pr63-final-capture',self.logs_dir/'final-state')
            manifest=json.loads((self.logs_dir/'final-state/manifest.json').read_text())
            for name, item in manifest['files'].items():
                p=self.logs_dir/'final-state'/name
                h=hashlib.sha256()
                with p.open('rb') as f:
                    for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
                assert h.hexdigest()==item['sha256'], name

class CapturedClaude(CaptureMixin,ClaudeCode):
    async def install(self, environment):
        # The caller supplies only the official existing executable, never a
        # home directory, account settings, model credentials, or sessions.
        executable=Path(os.environ['PR63_CLAUDE_BINARY'])
        await environment.upload_file(executable,'/tmp/pr63-claude')
        result=await environment.exec(command='install -m 0755 /tmp/pr63-claude /usr/local/bin/claude && rm /tmp/pr63-claude && claude --version',user='root',timeout_sec=120)
        if result.return_code:raise RuntimeError('offline Claude install failed')
        (self.logs_dir/'installed-version.txt').write_text(result.stdout or '')

class SmokeWork(BaseAgent):
    def __init__(self, task_dir, *args, **kwargs):
        self.task_dir=Path(task_dir)
        super().__init__(*args, **kwargs)
    @staticmethod
    def name():return 'pr63-capture-smoke'
    def version(self):return '1.0'
    async def setup(self,environment):pass
    async def run(self,instruction,environment,context):
        await environment.upload_dir(self.task_dir/'solution','/solution')
        result=await environment.exec(command='bash /solution/solve.sh',user='agent',timeout_sec=120)
        (self.logs_dir/'oracle.txt').write_text((result.stdout or '')+(result.stderr or ''))
        if result.return_code:raise RuntimeError('smoke Oracle application failed')

class CaptureSmoke(CaptureMixin,SmokeWork):
    async def run(self,instruction,environment,context):
        # Add one untracked file to prove the collection path actually works.
        await environment.exec(command="printf 'collector integration sentinel\\n' > /workspace/repo/pr63-collection-smoke.txt",user='agent')
        await super().run(instruction,environment,context)
