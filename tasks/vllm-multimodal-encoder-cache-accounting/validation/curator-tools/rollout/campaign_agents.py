"""Only harness installation differs from stock Harbor ClaudeCode."""
from pathlib import Path
from harbor.agents.installed.claude_code import ClaudeCode
from harbor.agents.base import BaseAgent

CLI=Path('/usr/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe')

async def install_cli(environment):
    await environment.upload_file(source_path=CLI,target_path='/tmp/pr84-claude.bin')
    result=await environment.exec(command='install -m 755 /tmp/pr84-claude.bin /usr/local/bin/claude && rm /tmp/pr84-claude.bin && /usr/local/bin/claude --version',user='root',timeout_sec=60)
    if result.return_code or '2.1.238' not in result.stdout:raise RuntimeError('offline Claude Code installation/version check failed')

class OfflineClaude(ClaudeCode):
    async def install(self,environment):
        await install_cli(environment)

class CollectionCanary(BaseAgent):
    @staticmethod
    def name(): return 'collection-canary'
    def version(self): return '1.0'
    def __init__(self,*args,oracle_patch,**kwargs):
        super().__init__(*args,**kwargs)
        self.oracle_patch=Path(oracle_patch)
    async def setup(self,environment):
        await install_cli(environment)
    async def run(self,instruction,environment,context):
        await environment.upload_file(source_path=self.oracle_patch,target_path='/tmp/pr84-canary.patch')
        result=await environment.exec(command='git apply /tmp/pr84-canary.patch',user='agent')
        if result.return_code:raise RuntimeError('Oracle patch application failed')
        result=await environment.exec(command="printf '\\ncollector tracked canary\\n' >> README.md; printf 'CANARY = True\\n' > review_collection_canary.py",user='agent')
        if result.return_code:raise RuntimeError('canary writes failed')
