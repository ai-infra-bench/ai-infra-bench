#!/usr/bin/env python3
"""Independent behavioral verifier. Run as root; candidate code runs as nobody.

Only public SDK/RPC results, actual model requests and ordinary workspace files
are observed. No candidate recovery journal layout is read or modified.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid

from scripted_provider import ScriptedProvider, tool

HERE = Path(__file__).resolve().parent
UID = GID = 65534
CASE_IDS = [
    'sdk_public_contract', 'disabled_regression', 'in_memory_rejected',
    'normal_files_and_conversation', 'checkpoint_branch_and_idempotence',
    'invalid_and_foreign_targets', 'idle_external_conflict',
    'idle_unrelated_changes_preserved', 'file_becomes_nested_directory', 'idle_descendant_conflict',
    'between_requests_external_conflict', 'failed_bash_changes',
    'cancelled_bash_changes', 'running_request_busy',
    'interrupted_request_recovery', 'first_request_interruption',
    'repeated_interrupted_resume', 'inflight_bash_recovery',
    'rollback_process_interruption', 'rollback_concurrent_prompt', 'filesystem_failure_retry',
    'steering_followup_single_checkpoint', 'rpc_cli_contract',
    'rpc_cli_resume_recovery', 'tui_rollback_command',
]


class SetupFailure(Exception):
    pass


def require(value, message):
    if not value:
        raise AssertionError(message)


def git(root, *args):
    return subprocess.check_output(['git', '-c', 'safe.directory=' + str(root), '-C', str(root), *args], stderr=subprocess.STDOUT).decode()


def file_state(path):
    if not path.exists():
        return None
    return {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'mode': path.stat().st_mode & 0o7777}


class Peer:
    def __init__(self, fixture, *, rpc=False, enable=True, in_memory=False, startup_arm=None, retry=False):
        self.fixture = fixture
        self.rpc = rpc
        self.events = []
        self.messages = []
        self.stderr = ''
        self.stdout_tail = ''
        self.condition = threading.Condition()
        self.serial = 0
        self.closed = False
        self.process = subprocess.Popen([sys.executable, str(HERE / 'process_supervisor.py'), '--uid', str(UID), '--gid', str(GID)],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._read_errors, daemon=True).start()
        self.wait(lambda: any(e.get('type') == 'ready' for e in self.events), 'supervisor ready', 15)
        argv = [fixture.runner.node]
        env = {'HOME': str(fixture.home), 'PI_CODING_AGENT_DIR': str(fixture.agent_dir),
               'PI_OFFLINE': '1', 'PI_TELEMETRY': '0', 'PI_NO_LOCAL_LLM': '1', 'NO_PROXY': '127.0.0.1,localhost',
               'no_proxy': '127.0.0.1,localhost', 'HTTP_PROXY': '', 'HTTPS_PROXY': '', 'http_proxy': '', 'https_proxy': '',
               'NODE_OPTIONS': '', 'TSX_TSCONFIG_PATH': str(fixture.runner.pi / 'tsconfig.json')}
        if rpc:
            argv += [str(fixture.runner.pi / 'packages/coding-agent/dist/cli.js'), '--mode', 'rpc', '--provider', 'rollback-test',
                     '--model', 'rollback-model', '--thinking', 'off', '--session', str(fixture.session_file),
                     '--no-extensions', '--no-skills', '--no-prompt-templates', '--no-context-files']
            if enable:
                argv.append('--safe-rollback')
        else:
            config = {'pi': str(fixture.runner.pi), 'cwd': str(fixture.project), 'agentDir': str(fixture.agent_dir),
                      'sessionFile': str(fixture.session_file), 'inMemory': in_memory, 'retry': retry}
            if enable is not None:
                config['enable'] = enable
            env['ROLLBACK_PEER_CONFIG'] = json.dumps(config)
            argv += [str(HERE / 'sdk_peer.mjs')]
        start_options={'argv':argv,'cwd':str(fixture.project),'env':env}
        if startup_arm is not None: start_options['arm']=startup_arm
        self.supervisor('start', **start_options)
        fixture.peers.append(self)
        if rpc:
            self.call('get_state', timeout=30)
            self.ready = {'kind': 'ready'}
        else:
            self.wait(lambda: any(m.get('kind') in ('ready', 'setup_error') for m in self.messages)
                      or (startup_arm is not None and any(e.get('type')=='trigger' for e in self.events)), 'SDK startup', 35)
            self.ready = next((m for m in self.messages if m.get('kind') in ('ready', 'setup_error')), {'kind':'interrupted_startup'})
            if self.ready['kind'] == 'setup_error' and not in_memory:
                raise AssertionError('Candidate SDK initialization failed: ' + self.ready['error'])

    def _read_errors(self):
        for line in self.process.stderr:
            self.stderr += line

    def _read(self):
        for line in self.process.stdout:
            try:
                event = json.loads(line)
            except ValueError:
                self.stderr += line
                continue
            with self.condition:
                self.events.append(event)
                if event.get('type') == 'output':
                    if event.get('stream') == 'stdout':
                        self.stdout_tail += event.get('data', '')
                        while '\n' in self.stdout_tail:
                            raw, self.stdout_tail = self.stdout_tail.split('\n', 1)
                            try:
                                self.messages.append(json.loads(raw))
                            except ValueError:
                                pass
                    else:
                        self.stderr += event.get('data', '')
                self.condition.notify_all()
        with self.condition:
            self.condition.notify_all()

    def wait(self, predicate, description, timeout=25, allow_exit=False):
        with self.condition:
            deadline = time.monotonic() + timeout
            exited_at = None
            supervisor_exited_at = None
            while not predicate():
                if self.process.poll() is not None:
                    if supervisor_exited_at is None: supervisor_exited_at=time.monotonic()
                    if time.monotonic()-supervisor_exited_at > .25:
                        raise SetupFailure(f'Supervisor exited unexpectedly while waiting for {description}; stderr={self.stderr[-2500:]}')
                if not allow_exit and any(e.get('type')=='execution_done' for e in self.events):
                    if exited_at is None: exited_at=time.monotonic()
                    if time.monotonic()-exited_at > .25:
                        raise AssertionError(f'Candidate execution ended before {description}; stderr={self.stderr[-1800:]}')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AssertionError(f'Timeout waiting for {description}; stderr={self.stderr[-1800:]}; messages={self.messages[-3:]}')
                self.condition.wait(min(remaining, 0.25))

    def supervisor(self, op, **args):
        self.serial += 1
        ident = f's{self.serial}'
        try:
            self.process.stdin.write(json.dumps({'id': ident, 'op': op, **args}) + '\n')
            self.process.stdin.flush()
        except (BrokenPipeError,OSError) as error:
            raise SetupFailure(f'Supervisor control channel failed during {op}: {error}; stderr={self.stderr[-2500:]}') from error
        self.wait(lambda: any(e.get('type') == 'reply' and e.get('id') == ident for e in self.events), f'supervisor {op}', 20, allow_exit=True)
        reply = next(e for e in self.events if e.get('type') == 'reply' and e.get('id') == ident)
        if not reply.get('ok'):
            if op in ('stdin','close_stdin'):
                raise AssertionError(f'Candidate input unavailable: {reply}')
            raise SetupFailure(f'Supervisor {op}: {reply}')
        return reply.get('result')

    def begin(self, op, **args):
        self.serial += 1
        ident = f'p{self.serial}'
        self.supervisor('stdin', data=json.dumps({'id': ident, ('type' if self.rpc else 'op'): op, **args}) + '\n')
        return ident

    def result(self, ident, timeout=25):
        self.wait(lambda: any(m.get('id') == ident and (m.get('type') == 'response' or m.get('kind') == 'reply') for m in self.messages), 'operation ' + ident, timeout)
        return next(m for m in self.messages if m.get('id') == ident and (m.get('type') == 'response' or m.get('kind') == 'reply'))

    def call(self, op, *, okay=True, timeout=25, **args):
        result = self.result(self.begin(op, **args), timeout)
        success = result.get('success') if self.rpc else result.get('ok')
        require(success is okay, f'{op} expected success={okay}: {result}')
        return result.get('data') if okay else result

    def require_api(self):
        require(all(self.ready.get('capabilities', {}).get(name) for name in ('listCheckpoints', 'getRollbackState', 'rollbackCheckpoint')),
                'Required public safe rollback SDK methods are absent')

    def list(self):
        records = self.call('list_checkpoints' if self.rpc else 'list')
        records = records['checkpoints'] if self.rpc else records
        require(isinstance(records, list), 'Checkpoint response is not a list')
        ids = []
        for record in records:
            require(isinstance(record, dict) and isinstance(record.get('id'), str) and record['id'], 'Invalid checkpoint ID')
            ids.append(record['id'])
        require(len(ids) == len(set(ids)), 'Duplicate checkpoint IDs')
        return records

    def state(self):
        state = self.call('get_rollback_state' if self.rpc else 'state')
        require(isinstance(state.get('enabled'), bool) and state.get('status') in ('ready','interrupted','restoring','blocked'), 'Invalid rollback state')
        return state

    def rollback(self, cp, okay=True, timeout=35):
        return self.call('rollback_checkpoint' if self.rpc else 'rollback', checkpointId=cp, okay=okay, timeout=timeout)

    def prompt(self, text):
        start = len(self.messages)
        ident = self.begin('prompt', **({'message':text} if self.rpc else {'text':text}))
        if self.rpc:
            result = self.result(ident)
            require(result.get('success'), f'RPC prompt rejected: {result}')
            # agent_settled is emitted after all retries and queued follow-ups.
            self.wait(lambda: any(m.get('type') == 'agent_settled' for m in self.messages[start:]), 'RPC agent settled', 35)
        else:
            result = self.result(ident, 35)
            require(result.get('ok'), f'Prompt rejected: {result}')

    def kill(self):
        if self.closed:
            return
        self.supervisor('kill')
        self.wait(lambda: any(e.get('type') == 'execution_done' for e in self.events), 'execution tree termination', 20)

    def close(self):
        if self.closed:
            return
        try:
            self.supervisor('shutdown')
        except Exception:
            self.process.kill()
        try:
            self.process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.process.kill()
        self.closed = True


class Fixture:
    def __init__(self, runner, name):
        self.runner = runner
        self.root = Path(tempfile.mkdtemp(prefix='rollback-' + name + '-', dir=runner.scratch))
        self.root.chmod(0o755)
        self.project = self.root / 'project'
        self.project.mkdir()
        self.home = self.root / 'home'
        self.agent_dir = self.home / '.pi/agent'
        self.agent_dir.mkdir(parents=True)
        self.session_file = self.root / 'sessions/current.jsonl'
        self.session_file.parent.mkdir()
        self.peers = []
        self.provider = ScriptedProvider()
        self.nonce = uuid.uuid4().hex
        files = {'.gitignore': 'ignored/\n', 'a.txt': f'original-a-{self.nonce}\n',
                 'b.txt': f'original-b-{self.nonce}\n', 'delete.txt': 'delete baseline\n',
                 'rename.txt': 'rename baseline\n', 'mode.sh': '#!/bin/sh\necho original\n',
                 'nested/item.txt': 'nested baseline\n', '__proto__': 'ordinary filename baseline\n'}
        for name, content in files.items():
            path = self.project / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        os.chmod(self.project / 'mode.sh', 0o755)
        git(self.project, 'init', '-q')
        git(self.project, 'config', 'user.email', 'fixture@example.invalid')
        git(self.project, 'config', 'user.name', 'Fixture')
        git(self.project, 'add', '.')
        git(self.project, 'commit', '-qm', 'fixture')
        (self.project / 'a.txt').write_text(f'preexisting-uncommitted-{self.nonce}\n')
        (self.project / 'untracked.txt').write_bytes(b'preexisting-untracked\x00bytes\xff')
        (self.project / 'ignored').mkdir()
        (self.project / 'ignored/cache').write_text('outside rollback scope')
        self.names = list(files) + ['untracked.txt']
        self.baseline = {name: file_state(self.project / name) for name in self.names}
        self.git_baseline = self.git_state()
        config = {'providers': {'rollback-test': {'baseUrl':self.provider.url, 'api':'openai-completions', 'apiKey':'local-test',
                  'models':[{'id':'rollback-model','name':'Rollback model','reasoning':False,'input':['text'],
                             'cost':{'input':0,'output':0,'cacheRead':0,'cacheWrite':0},'contextWindow':100000,'maxTokens':2048,
                             'compat':{'supportsDeveloperRole':False,'supportsStore':False}}]}}}
        (self.agent_dir / 'models.json').write_text(json.dumps(config))
        (self.agent_dir / 'auth.json').write_text('{}')
        (self.agent_dir / 'settings.json').write_text(json.dumps({'compaction':{'enabled':False},'retry':{'enabled':False}}))
        self.chown()

    def chown(self):
        for root, dirs, files in os.walk(self.root):
            os.chown(root, UID, GID)
            for name in files:
                os.chown(Path(root) / name, UID, GID)

    def git_state(self):
        return [git(self.project, 'rev-parse', 'HEAD'), git(self.project, 'rev-parse', '--symbolic-full-name', 'HEAD'),
                git(self.project, 'for-each-ref', '--format=%(refname) %(objectname)', 'refs/heads/'),
                git(self.project, 'ls-files', '--stage')]

    def peer(self, **kwargs):
        return Peer(self, **kwargs)

    def assert_baseline(self, absent=()):
        for name, state in self.baseline.items():
            require(file_state(self.project / name) == state, 'Did not restore baseline: ' + name)
        for name in list(absent)+['constructor']:
            require(not (self.project / name).exists(), 'Created file survived rollback: ' + name)
        require(self.git_state() == self.git_baseline, 'Git HEAD/branches/index entries changed')

    def mutation(self, peer, label='request', extra=None):
        steps = [tool('write', path='a.txt', content='changed-' + self.nonce),
                 tool('edit', path='b.txt', edits=[{'oldText':f'original-b-{self.nonce}', 'newText':'edited-' + self.nonce}]),
                 tool('bash', command="rm delete.txt; mv rename.txt renamed.txt; printf 'new bytes' > created.txt; chmod 600 mode.sh; printf 'replacement' > untracked.txt; printf 'ignored updated' > ignored/cache; printf 'special updated' > __proto__; printf 'created special' > constructor"),
                 {'text':'completed-' + label}]
        if extra:
            steps[-1:] = extra
        self.provider.script(*steps)
        peer.prompt(label + '-' + self.nonce)
        require((self.project/'a.txt').read_text()=='changed-'+self.nonce,'Built-in write did not execute')
        require((self.project/'b.txt').read_text()=='edited-'+self.nonce+'\n','Built-in edit did not execute')
        require(not (self.project/'delete.txt').exists() and not (self.project/'rename.txt').exists(),'Bash deletion/rename did not execute')
        require((self.project/'renamed.txt').read_text()=='rename baseline\n','Bash rename target incorrect')
        require((self.project/'created.txt').read_text()=='new bytes','Bash creation did not execute')
        require((self.project/'mode.sh').stat().st_mode & 0o7777 == 0o600,'Bash permission change did not execute')
        require((self.project/'untracked.txt').read_text()=='replacement','Untracked file write did not execute')
        require((self.project/'__proto__').read_text()=='special updated','Ordinary special-name file was not written')
        require((self.project/'constructor').read_text()=='created special','Ordinary special-name file was not created')

    def no_provider_errors(self):
        require(not self.provider.errors, 'Provider transport errors: ' + repr(self.provider.errors))

    def close(self):
        for peer in self.peers:
            peer.close()
        self.provider.close()


def assert_no_text(payload, text):
    require(text not in json.dumps(payload), 'Rolled-back conversation leaked into effective context: ' + text)


def assert_conversation_restored(peer, before_messages):
    def content(items):
        return [{key:message[key] for key in ('role','content','toolCallId','toolName','isError') if key in message} for message in items]
    require(content(peer.call('inspect')['messages'])==content(before_messages),'Rollback restored a different effective conversation')


def new_checkpoint(peer, before_ids):
    created={checkpoint['id'] for checkpoint in peer.list()}-set(before_ids)
    require(len(created)==1,'Expected exactly one new stable checkpoint ID per request')
    return created.pop()


def sdk_public_contract(f):
    p = f.peer(); p.require_api()
    state=p.state(); require(state['enabled'] and state['status']=='ready', 'New enabled session not ready')
    p.list()
    before=p.call('inspect')['messages']
    f.provider.script({'text':'hello'})
    p.prompt('one-' + f.nonce)
    cp = p.list(); require(len(cp)==1,'Expected one checkpoint per request')
    p.rollback(cp[0]['id'])
    assert_conversation_restored(p,before)


def disabled_regression(f):
    p = f.peer(enable=False); p.require_api()
    state=p.state(); require(state['enabled'] is False and state['status']=='ready','Disabled state mismatch')
    require(p.list()==[],'Disabled checkpoints not empty')
    f.mutation(p)
    p.rollback('missing',okay=False)
    require((f.project/'a.txt').read_text()=='changed-'+f.nonce,'Disabled rollback changed file')
    require(p.list()==[],'Disabled prompt created checkpoint')


def in_memory_rejected(f):
    normal=f.peer(); normal.require_api(); normal.close()
    p = f.peer(in_memory=True)
    require(p.ready.get('kind')=='setup_error','Enabled in-memory session accepted')
    require(bool(p.ready.get('error','').strip()), 'In-memory rejection had no explanation')


def normal_files_and_conversation(f):
    p = f.peer(); p.require_api(); f.mutation(p, 'discard-me')
    cp = p.list(); require(len(cp)==1,'Wrong checkpoint count after multi-turn request')
    require((f.project/'a.txt').read_text()=='changed-'+f.nonce,'Built-in write did not execute')
    p.rollback(cp[0]['id']); f.assert_baseline(['created.txt','renamed.txt'])
    require((f.project/'ignored/cache').read_text()=='ignored updated','Rollback touched ignored untracked file')
    assert_no_text(p.call('inspect')['messages'], 'discard-me-' + f.nonce)
    p.kill(); p.close()
    p = f.peer(enable=None)
    require(p.state()['enabled'] and p.state()['status']=='ready','Restored enabled/ready state not durable')
    f.assert_baseline(['created.txt','renamed.txt'])
    f.provider.script({'text':'continued'})
    p.prompt('continuation-'+f.nonce)
    assert_no_text(f.provider.requests[-1], 'discard-me-'+f.nonce)


def checkpoint_branch_and_idempotence(f):
    p = f.peer(); p.require_api()
    f.provider.script(tool('write',path='a.txt',content='branch-a'),{'text':'a'})
    p.prompt('first-'+f.nonce); first=p.list()[0]['id']
    before_second=p.call('inspect')['messages']
    f.provider.script(tool('write',path='a.txt',content='branch-b'),{'text':'b'})
    p.prompt('abandoned-'+f.nonce); cps=p.list(); require(len(cps)==2,'Second checkpoint absent')
    abandoned=new_checkpoint(p,{first})
    p.rollback(abandoned)
    require((f.project/'a.txt').read_text()=='branch-a','Second checkpoint restored the wrong file boundary')
    assert_conversation_restored(p,before_second)
    p.rollback(first); p.rollback(first); f.assert_baseline()
    before_branch={checkpoint['id'] for checkpoint in p.list()}
    before_branch_messages=p.call('inspect')['messages']
    f.provider.script(tool('write',path='a.txt',content='branch-c'),{'text':'c'})
    p.prompt('new-branch-'+f.nonce)
    branch=new_checkpoint(p,before_branch)
    require(abandoned not in [c['id'] for c in p.list()], 'Abandoned checkpoint remains eligible')
    before=p.call('inspect')['messages']; p.rollback(abandoned,okay=False)
    require((f.project/'a.txt').read_text()=='branch-c' and p.call('inspect')['messages']==before,'Invalid branch rollback had side effects')
    assert_no_text(f.provider.requests[-1], 'abandoned-'+f.nonce)
    f.provider.script(tool('write',path='a.txt',content='branch-d'),{'text':'d'})
    p.prompt('new-branch-second-'+f.nonce)
    require((f.project/'a.txt').read_text()=='branch-d','Second request on new branch did not execute')
    p.rollback(branch); f.assert_baseline()
    assert_conversation_restored(p,before_branch_messages)


def invalid_and_foreign_targets(f):
    p=f.peer(); p.require_api(); f.provider.script({'text':'one'}); p.prompt('one')
    before=p.call('inspect')['messages']; p.rollback('foreign-'+uuid.uuid4().hex,okay=False)
    require(p.call('inspect')['messages']==before,'Invalid ID changed conversation'); f.assert_baseline()
    other=Fixture(f.runner,'foreign')
    try:
        q=other.peer(); q.require_api(); other.provider.script({'text':'other'}); q.prompt('other')
        p.rollback(q.list()[0]['id'],okay=False)
        require(p.call('inspect')['messages']==before,'Foreign-session ID changed conversation'); f.assert_baseline()
    finally: other.close()
    f.provider.script(tool('write',path='a.txt',content='ancestor-a'),{'text':'ancestor a complete'})
    p.prompt('ancestor-a-'+f.nonce)
    entry=next(entry for entry in p.call('inspect')['entries']
               if entry.get('type')=='message' and entry.get('message',{}).get('role')=='user'
               and 'ancestor-a-'+f.nonce in json.dumps(entry['message']))
    before_descendant={checkpoint['id'] for checkpoint in p.list()}
    f.provider.script(tool('write',path='a.txt',content='descendant-b'),{'text':'descendant b complete'})
    p.prompt('descendant-b-'+f.nonce); descendant=new_checkpoint(p,before_descendant)
    p.call('navigate',entryId=entry['id'])
    require(descendant not in [cp['id'] for cp in p.list()],
            'Checkpoint outside the active ancestor chain remains eligible after normal navigation')
    before=p.call('inspect'); files={name:file_state(f.project/name) for name in f.names}
    p.rollback(descendant,okay=False)
    require(p.call('inspect')['messages']==before['messages'] and p.call('inspect')['leafId']==before['leafId'],
            'Rejected non-ancestor checkpoint changed conversation')
    require(files=={name:file_state(f.project/name) for name in f.names},'Rejected non-ancestor checkpoint changed files')
    require(f.git_state()==f.git_baseline,'Rejected non-ancestor checkpoint changed Git state')


def idle_external_conflict(f):
    p=f.peer(); p.require_api(); f.mutation(p)
    (f.project/'a.txt').write_text('human-'+f.nonce)
    (f.project/'unrelated-user.txt').write_text('keep unrelated')
    before={name:file_state(f.project/name) for name in f.names+['created.txt','renamed.txt','constructor','unrelated-user.txt']}
    messages=p.call('inspect')['messages']
    checkpoint=p.list()[0]['id']
    rejection=p.rollback(checkpoint,okay=False)
    require('a.txt' in json.dumps([rejection,p.state()]),'Conflict path missing')
    require(p.call('inspect')['messages']==messages,'Conflict changed conversation')
    require(before=={name:file_state(f.project/name) for name in before},'Conflict partially changed files')
    # Resolve only the overlapping idle edit, leaving unrelated human work in
    # place. A diagnostic state label must not decide whether refusal was safe.
    (f.project/'a.txt').write_text('changed-'+f.nonce)
    p.rollback(checkpoint); f.assert_baseline(['created.txt','renamed.txt'])
    require(file_state(f.project/'unrelated-user.txt')==before['unrelated-user.txt'],'Conflict retry changed unrelated human work')


def between_requests_external_conflict(f):
    p=f.peer(); p.require_api()
    f.provider.script(tool('write',path='a.txt',content='first'),{'text':'first'}); p.prompt('first')
    first=p.list()[0]['id']
    (f.project/'a.txt').write_text('human-between-'+f.nonce)
    f.provider.script(tool('write',path='a.txt',content='second'),{'text':'second'}); p.prompt('second')
    cps=p.list(); require(len(cps)==2,'Expected two checkpoints')
    second=new_checkpoint(p,{first})
    messages=p.call('inspect')['messages']; rejection=p.rollback(first,okay=False)
    require('a.txt' in json.dumps([rejection,p.state()]),'Between-request conflict not identified')
    require((f.project/'a.txt').read_text()=='second' and messages==p.call('inspect')['messages'],'Between-request conflict mutated state')
    p.rollback(second); require((f.project/'a.txt').read_text()=='human-between-'+f.nonce,'Latest checkpoint did not preserve human baseline')


def idle_unrelated_changes_preserved(f):
    p=f.peer(); p.require_api(); f.mutation(p,'unrelated-idle')
    (f.project/'nested/item.txt').write_text('human-unrelated-'+f.nonce)
    (f.project/'human-only.txt').write_text('created-by-human-'+f.nonce)
    expected=dict(f.baseline)
    expected['nested/item.txt']=file_state(f.project/'nested/item.txt')
    expected['human-only.txt']=file_state(f.project/'human-only.txt')
    p.rollback(p.list()[0]['id'])
    for name,state in expected.items():
        require(file_state(f.project/name)==state,'Rollback failed to preserve unrelated idle change: '+name)
    require(all(not (f.project/name).exists() for name in ('created.txt','renamed.txt','constructor')),'Task-created files survived')
    require(f.git_state()==f.git_baseline,'Git state changed')


def file_becomes_nested_directory(f):
    p=f.peer(); p.require_api()
    f.provider.script(tool('bash',command="rm a.txt; mkdir -p a.txt/deep; printf owned > a.txt/deep/created.txt; rm nested/item.txt; rmdir nested; printf replacement > nested"),{'text':'done'})
    p.prompt('replace-file-with-tree-'+f.nonce)
    require((f.project/'a.txt/deep/created.txt').read_text()=='owned','Real Bash did not create nested tree')
    require((f.project/'nested').is_file() and (f.project/'nested').read_text()=='replacement',
            'Real Bash did not replace original directory with regular file')
    p.rollback(p.list()[0]['id']); f.assert_baseline(); p.kill(); p.close()
    p=f.peer(enable=None); require(p.state()['status']=='ready','Restored shape not durable'); f.assert_baseline()
    f.provider.script({'text':'continued'}); p.prompt('continue')
    assert_no_text(f.provider.requests[-1],'replace-file-with-tree-'+f.nonce)


def idle_descendant_conflict(f):
    p=f.peer(); p.require_api()
    f.provider.script(tool('bash',command="rm a.txt; mkdir -p a.txt/deep; printf owned > a.txt/deep/created.txt"),{'text':'done'})
    p.prompt('shape-before-idle-edit-'+f.nonce)
    manual=f.project/'a.txt/deep/idle-user.txt'; manual.write_text('preserve-human-'+f.nonce)
    before=p.call('inspect')['messages']; rejection=p.rollback(p.list()[0]['id'],okay=False)
    require(manual.read_text()=='preserve-human-'+f.nonce,'Idle user file overwritten')
    require((f.project/'a.txt/deep/created.txt').read_text()=='owned','Descendant conflict allowed partial rollback')
    require(p.call('inspect')['messages']==before,'Descendant conflict changed conversation')
    require('a.txt/deep/idle-user.txt' in json.dumps([rejection,p.state()]),'Descendant conflict path not identified')


def failed_bash_changes(f):
    p=f.peer(); p.require_api()
    f.provider.script(tool('bash',command="printf failed > a.txt; rm delete.txt; printf new > failed-new.txt; exit 19"),{'text':'observed failure'})
    p.prompt('failed shell')
    require((f.project/'a.txt').read_text()=='failed' and (f.project/'failed-new.txt').read_text()=='new' and not (f.project/'delete.txt').exists(),'Failed Bash did not preserve preceding writes')
    results=[m for m in f.provider.requests[-1].get('messages',[]) if m.get('role')=='tool']
    require('19' in json.dumps(results),'Bash exit code was not delivered to model')
    p.rollback(p.list()[0]['id']); f.assert_baseline(['failed-new.txt'])


def wait_file(path, predicate=lambda p:p.exists(), timeout=20):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if predicate(path): return
        time.sleep(0.03)
    raise AssertionError('Expected filesystem barrier was not reached: '+str(path))


def blocking_bash(f,p):
    fifo=f.root/'gate.fifo'; os.mkfifo(fifo); os.chown(fifo,UID,GID)
    command=f"printf 'inflight-{f.nonce}' > a.txt; printf before-stop > interrupted-new.txt; rm delete.txt; mv rename.txt renamed.txt; chmod 600 mode.sh; printf ready > gate-ready.txt; read x < '{fifo}'"
    f.provider.script(tool('bash',command=command),{'text':'should not execute before release'})
    ident=p.begin('prompt',text='interrupted-'+f.nonce)
    wait_file(f.project/'gate-ready.txt')
    require((f.project/'a.txt').read_text()=='inflight-'+f.nonce,'Shell barrier lacked preceding mutation')
    return ident


def cancelled_bash_changes(f):
    p=f.peer(); p.require_api(); ident=blocking_bash(f,p)
    p.call('abort'); p.result(ident)
    require(p.call('inspect')['isIdle'],'Abort did not settle')
    p.rollback(p.list()[0]['id']); f.assert_baseline(['interrupted-new.txt','renamed.txt','gate-ready.txt'])


def running_request_busy(f):
    p=f.peer(); p.require_api(); f.provider.script({'hold':True,'text':'done'})
    ident=p.begin('prompt',text='active')
    f.provider.wait_requests(1); cp=p.list()[0]['id']; before=p.call('inspect')['messages']
    p.rollback(cp,okay=False); require(p.call('inspect')['messages']==before,'Busy rollback changed messages'); f.assert_baseline()
    f.provider.releases[-1].set(); require(p.result(ident)['ok'],'Held prompt failed')


def assert_interrupted_gate(f,p):
    state=p.state(); require(state['enabled'] and state['status']=='interrupted','Unfinished request not marked interrupted')
    assert_recovery_commands_reject(f,p)


def assert_recovery_commands_reject(f,p):
    count=len(f.provider.requests); before=p.call('inspect')['messages']
    p.call('prompt',text='forbidden-new-request',okay=False)
    p.call('bash',command='printf forbidden > forbidden.txt',okay=False)
    entries=p.call('inspect')['entries']
    targets=[e['id'] for e in entries if e.get('type')=='message' and e.get('message',{}).get('role')=='user']
    if targets:
        p.call('navigate',entryId=targets[0],okay=False)
        p.call('fork',entryId=targets[0],okay=False)
    p.call('compact',okay=False)
    require(len(f.provider.requests)==count,'Recovery gate called model')
    require(p.call('inspect')['messages']==before,'Recovery gate allowed context mutation')
    require(not (f.project/'forbidden.txt').exists(),'Recovery gate allowed shell write')


def interrupted_request_recovery(f):
    p=f.peer(); p.require_api()
    f.provider.script(tool('write',path='a.txt',content='interrupted-write'),{'hold':True,'text':'end'})
    p.begin('prompt',text='discard-interrupted-'+f.nonce); f.provider.wait_requests(2)
    cp=p.list()[0]['id']; p.kill(); p.close()
    require((f.project/'a.txt').read_text()=='interrupted-write','Crash fixture did not retain tool changes')
    p=f.peer(enable=None); assert_interrupted_gate(f,p)
    require(p.list()[0]['id']==cp,'Checkpoint ID changed across restart')
    require((f.project/'a.txt').read_text()=='interrupted-write','Resume discarded work before user chose checkpoint')
    p.rollback(cp); f.assert_baseline(); p.kill(); p.close()
    p=f.peer(enable=None); require(p.state()['status']=='ready','Completed rollback not durable'); f.assert_baseline()
    f.provider.script({'text':'continue'}); p.prompt('continue-'+f.nonce)
    assert_no_text(f.provider.requests[-1],'discard-interrupted-'+f.nonce)


def inflight_bash_recovery(f):
    p=f.peer(); p.require_api(); blocking_bash(f,p); cp=p.list()[0]['id']; p.kill(); p.close()
    # Discard the scripted completion which the killed process never requested.
    with f.provider.condition: f.provider.steps=[]
    p=f.peer(enable=None); assert_interrupted_gate(f,p); p.rollback(cp)
    f.assert_baseline(['interrupted-new.txt','renamed.txt','gate-ready.txt'])


def first_request_interruption(f):
    p=f.peer(); p.require_api()
    f.provider.script({'hold':True,'text':'never delivered'})
    p.begin('prompt',text='first-interrupted-'+f.nonce); f.provider.wait_requests(1)
    cp=p.list()[0]['id']; p.kill(); p.close()
    p=f.peer(enable=None); assert_interrupted_gate(f,p)
    require(p.list()[0]['id']==cp,'First request checkpoint was lost before first assistant response')
    p.rollback(cp); f.assert_baseline()
    f.provider.script({'text':'next'}); p.prompt('next')
    assert_no_text(f.provider.requests[-1],'first-interrupted-'+f.nonce)


def repeated_interrupted_resume(f):
    p=f.peer(); p.require_api()
    f.provider.script(tool('write',path='a.txt',content='still-interrupted-'+f.nonce),{'hold':True,'text':'not finished'})
    p.begin('prompt',text='repeated-resume-'+f.nonce); f.provider.wait_requests(2)
    cp=p.list()[0]['id']; p.kill(); p.close()
    for _ in range(2):
        p=f.peer(enable=None); assert_interrupted_gate(f,p)
        require(p.list()[0]['id']==cp,'Checkpoint changed while awaiting rollback choice')
        require((f.project/'a.txt').read_text()=='still-interrupted-'+f.nonce,'Repeated resume discarded work before user chose')
        p.kill(); p.close()
    p=f.peer(enable=None); assert_interrupted_gate(f,p); p.rollback(cp); f.assert_baseline()
    f.provider.script({'text':'next'}); p.prompt('next')
    assert_no_text(f.provider.requests[-1],'repeated-resume-'+f.nonce)


def rollback_process_interruption(f):
    p=f.peer(); p.require_api(); f.mutation(p,'rollback-killed'); cp=p.list()[0]['id']
    p.supervisor('arm',workspace=str(f.project),paths=f.names+['created.txt','renamed.txt','constructor'],tag='during-restore')
    p.begin('rollback',checkpointId=cp)
    p.wait(lambda:any(e.get('type')=='trigger' and e.get('tag')=='during-restore' for e in p.events),'restore mutation trigger',35)
    p.wait(lambda:any(e.get('type')=='execution_done' for e in p.events),'killed restoring execution',20)
    p.close()
    # Kill a second recovery attempt only when another public file mutation
    # actually occurs. A valid atomic restore may have restored all files in
    # the first observed mutation; it need not manufacture extra writes.
    p=f.peer(enable=None,startup_arm={'workspace':str(f.project),'paths':f.names+['created.txt','renamed.txt','constructor'],'tag':'startup-restore'})
    if p.ready.get('kind')!='interrupted_startup':
        all_restored=all(file_state(f.project/name)==state for name,state in f.baseline.items()) and all(not (f.project/name).exists() for name in ('created.txt','renamed.txt','constructor'))
        if not all_restored:
            p.wait(lambda:any(e.get('type')=='trigger' for e in p.events),'second restoration mutation',35)
    if any(e.get('type')=='trigger' for e in p.events):
        p.wait(lambda:any(e.get('type')=='execution_done' for e in p.events),'second interrupted recovery terminated',20)
        p.close(); p=None
    else:
        p.supervisor('disarm')
    def check_request(payload):
        f.assert_baseline(['created.txt','renamed.txt'])
        assert_no_text(payload,'rollback-killed-'+f.nonce)
    f.provider.request_check=check_request
    if p is None: p=f.peer(enable=None)
    # Both synchronous startup recovery and observable asynchronous recovery
    # are valid. A prompt may reject while restoring, or wait for completion.
    f.provider.script({'text':'after restore'})
    response=p.result(p.begin('prompt',text='after restore'),35)
    deadline=time.monotonic()+25
    while p.state()['status']!='ready':
        require(time.monotonic()<deadline,'Startup recovery did not complete automatically')
        time.sleep(.03)
    if not response.get('ok'):
        p.prompt('after restore')
    require(not f.provider.errors,'Model ran before complete restoration: '+repr(f.provider.errors))
    f.assert_baseline(['created.txt','renamed.txt'])
    assert_no_text(f.provider.requests[-1],'rollback-killed-'+f.nonce)


def filesystem_failure_retry(f):
    p=f.peer(); p.require_api()
    f.provider.script(tool('write',path='a.txt',content='changed'),{'text':'done'}); p.prompt('permission failure')
    cp=p.list()[0]['id']
    before_files={name:file_state(f.project/name) for name in f.names}
    before_messages=p.call('inspect')['messages']
    # Ordinary EACCES without changing ANY protected regular-file permission
    # bits/content. Deny in-place writes and rename replacement alike. Keep the
    # session/config directories writable; never touch candidate private data.
    protected=[f.root,f.project,f.project/'a.txt']
    attrs={path:(path.stat().st_uid,path.stat().st_gid,path.stat().st_mode & 0o7777) for path in protected}
    for path in protected:
        os.chown(path,0,0)
        if path.is_dir(): os.chmod(path,0o555)
    try:
        p.rollback(cp,okay=False)
        state=p.state()
        require(state['status'] in ('blocked','restoring','ready'),'Failure state not inspectable')
        if state['status']=='ready':
            require(before_files=={name:file_state(f.project/name) for name in f.names} and before_messages==p.call('inspect')['messages'],'Ready preflight failure partially mutated state')
        else:
            p.kill(); p.close(); p=f.peer(enable=None)
            deadline=time.monotonic()+20
            while p.state()['status']=='restoring':
                require(time.monotonic()<deadline,'Unresolved filesystem failure remained indefinitely uninspectable')
                time.sleep(.03)
            require(p.state()['status']=='blocked','Failed pending recovery was not retained across restart')
            assert_recovery_commands_reject(f,p)
    finally:
        for path,(uid,gid,mode) in attrs.items():
            os.chown(path,uid,gid); os.chmod(path,mode)
    p.rollback(cp); f.assert_baseline()


def rollback_concurrent_prompt(f):
    p=f.peer(); p.require_api(); f.mutation(p,'concurrent-discard')
    cp=p.list()[0]['id']
    def check_request(payload):
        f.assert_baseline(['created.txt','renamed.txt'])
        assert_no_text(payload,'concurrent-discard-'+f.nonce)
    f.provider.request_check=check_request
    f.provider.script({'text':'after rollback'})
    rollback_id=p.begin('rollback',checkpointId=cp)
    prompt_id=p.begin('prompt',text='concurrent continuation')
    require(p.result(rollback_id,35).get('ok'),'Rollback did not complete')
    response=p.result(prompt_id,35)
    if not response.get('ok'):
        p.prompt('continuation after busy rejection')
    require(not f.provider.errors,'Concurrent prompt saw unfinished rollback: '+repr(f.provider.errors))
    f.assert_baseline(['created.txt','renamed.txt'])


def steering_followup_single_checkpoint(f):
    p=f.peer(retry=True); p.require_api()
    f.provider.script({'status':503,'message':'Service unavailable: retry fixture'},
                      {'hold':True,'text':'first'}, {'text':'second'}, {'text':'third'})
    ident=p.begin('prompt',text='main-'+f.nonce); f.provider.wait_requests(2)
    p.wait(lambda:any(m.get('event',{}).get('type')=='auto_retry_start' for m in p.messages), 'actual session retry')
    checkpoints=p.list(); require(len(checkpoints)==1,'Retry created extra checkpoint')
    p.call('steer',text='steering-'+f.nonce); p.call('follow_up',text='queued-'+f.nonce)
    f.provider.releases[-1].set(); require(p.result(ident,35)['ok'],'Queued request execution failed')
    require([cp['id'] for cp in p.list()]==[checkpoints[0]['id']],'Retry/steering/follow-up changed checkpoint boundary')
    require(any(m.get('event',{}).get('type')=='auto_retry_end' and m['event'].get('success') for m in p.messages),
            'Retry never completed successfully')
    text=json.dumps(p.call('inspect')['messages'])
    require('steering-'+f.nonce in text and 'queued-'+f.nonce in text,'Queued requests were not executed')
    p.rollback(p.list()[0]['id'])
    f.provider.script({'text':'new'}); p.prompt('new')
    for tag in ('main-','steering-','queued-'): assert_no_text(f.provider.requests[-1],tag+f.nonce)


def rpc_cli_contract(f):
    p=f.peer(rpc=True)
    require(p.state()['enabled'],'CLI flag did not enable rollback')
    f.provider.script(tool('write',path='a.txt',content='rpc-change'),{'text':'done'})
    p.prompt('rpc-discard-'+f.nonce); cp=p.list()[0]['id']; p.rollback(cp)
    f.assert_baseline()
    p.rollback('invalid',okay=False)
    f.provider.script({'text':'continued'}); p.prompt('rpc-continue')
    assert_no_text(f.provider.requests[-1],'rpc-discard-'+f.nonce)


def rpc_cli_resume_recovery(f):
    p=f.peer(rpc=True)
    f.provider.script(tool('write',path='a.txt',content='rpc-incomplete'),{'hold':True,'text':'done'})
    p.begin('prompt',message='rpc-interrupted-'+f.nonce); f.provider.wait_requests(2)
    cp=p.list()[0]['id']; p.kill(); p.close()
    p=f.peer(rpc=True,enable=None); require(p.state()['status']=='interrupted','RPC resume missing recovery gate')
    p.call('prompt',message='not allowed',okay=False)
    p.rollback(cp); f.assert_baseline(); p.kill(); p.close()
    p=f.peer(rpc=True,enable=None); require(p.state()['status']=='ready','RPC rollback not durable'); f.assert_baseline()


def tui_rollback_command(f):
    from tui_case import run
    run(f)


class Runner:
    def __init__(self,args):
        self.pi=Path(args.workspace).resolve(); self.node=args.node
        self.output=Path(args.output_dir).resolve(); self.output.mkdir(parents=True,exist_ok=True)
        self.scratch=Path(tempfile.mkdtemp(prefix='pi-rollback-fixtures-',dir=args.scratch)); self.scratch.chmod(0o755)
        self.results=[]

    def run(self, ids):
        for ident in ids:
            started=time.monotonic(); fixture=None
            try:
                fixture=Fixture(self,ident)
                globals()[ident](fixture)
                fixture.no_provider_errors()
                result={'id':ident,'passed':True}
            except Exception as exc:
                result={'id':ident,'passed':False,'failure_kind':'environment' if isinstance(exc,SetupFailure) else 'behavior',
                        'error':str(exc),'traceback':traceback.format_exc()}
            finally:
                if fixture:
                    logs={'provider_requests':fixture.provider.requests,'provider_errors':fixture.provider.errors,
                          'peers':[{'messages':p.messages,'events':p.events,'stderr':p.stderr} for p in fixture.peers]}
                    (self.output/(ident+'.json')).write_text(json.dumps(logs,indent=2))
                    fixture.close()
            result['seconds']=round(time.monotonic()-started,3)
            self.results.append(result); print(json.dumps(result),flush=True)
        summary={'expected_cases':ids,'results':self.results,'passed':all(r['passed'] for r in self.results),'scratch':str(self.scratch)}
        (self.output/'behavior-results.json').write_text(json.dumps(summary,indent=2))
        return summary['passed']


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--workspace',default='/workspace/pi'); parser.add_argument('--output-dir',default='/logs/verifier/behavior')
    parser.add_argument('--node',default=shutil.which('node')); parser.add_argument('--scratch',default='/tmp')
    parser.add_argument('--case',action='append',choices=CASE_IDS)
    args=parser.parse_args()
    if os.geteuid()!=0: raise SystemExit('Verifier coordinator must run as root')
    if not args.node: raise SystemExit('Node runtime unavailable')
    return 0 if Runner(args).run(args.case or CASE_IDS) else 1


if __name__=='__main__':
    raise SystemExit(main())
