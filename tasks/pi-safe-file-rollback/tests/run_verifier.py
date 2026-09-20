#!/usr/bin/env python3
"""Root scoring coordinator: freeze inputs, build offline, require complete reports."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

BASE = 'd981de1229ef899957bbe968bc8dcda02a21f477'
HERE = Path(__file__).resolve().parent
PI = Path('/workspace/pi')
LOG = Path('/logs/verifier')
UID = GID = 65534


def git(*args):
    return subprocess.check_output(['/usr/bin/git', '--no-replace-objects', '-c', 'safe.directory='+str(PI),
                                    '-c', 'core.fsmonitor=false', '-C', str(PI), *args])


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def dependency_digest():
    records=[]
    def visit(path):
        for item in sorted(path.iterdir()):
            if item.name in ('.vite','.vite-temp','.cache'): continue
            relative=str(item.relative_to(PI))
            if item.is_symlink(): records.append([relative,'link',os.readlink(item)])
            elif item.is_dir(): visit(item)
            elif item.is_file():
                # node-gyp writes the prerequisite list of its generated build/Makefile in a
                # non-deterministic order, so that one file differs between two builds of the
                # same Dockerfile (seen: node_modules/ssh2/lib/protocol/crypto/build/Makefile)
                # and made the pin match a single image only. It is a build log of the addon,
                # not code that runs; the compiled addon next to it stays covered.
                if item.name=='Makefile' and item.parent.name=='build' and (item.parent/'config.gypi').is_file(): continue
                records.append([relative,'file',hashlib.sha256(item.read_bytes()).hexdigest()])
    def discover(path):
        for item in sorted(path.iterdir()):
            if item.name=='.git' or item.is_symlink(): continue
            if item.is_dir():
                if item.name=='node_modules': visit(item)
                else: discover(item)
    discover(PI)
    visit(PI/'packages/ai/src/providers/data')
    return digest(records)


def outcomes(path):
    root=ET.parse(path).getroot(); result={}
    for case in root.findall('.//testcase'):
        key=case.get('classname','')+'::'+case.get('name','')
        if key in result: raise ValueError('Duplicate testcase: '+key)
        result[key]='skipped' if case.find('skipped') is not None else 'failed' if any(case.find(k) is not None for k in ('failure','error')) else 'passed'
    if not result: raise ValueError('Empty test inventory')
    suites=[root] if root.tag=='testsuite' else root.findall('testsuite')
    if sum(int(s.get('tests',0)) for s in suites)!=len(result): raise ValueError('Incomplete JUnit inventory')
    return result


def known_timestamp_failures(path, pins):
    """Recognize only the independently reproduced Base stale-value signature."""
    known=pins['timestamp_sensitive_regression']
    accepted=[]
    for case in ET.parse(path).getroot().findall('.//testcase'):
        key=case.get('classname','')+'::'+case.get('name','')
        if key!=known['case'] or case.find('skipped') is not None or case.find('error') is not None:
            continue
        failures=case.findall('failure')
        if failures and all(f.get('type')=='AssertionError' and f.get('message')==known['failure_message']
                            and known['source_location'] in (f.text or '') for f in failures):
            accepted.append(key)
    return accepted


def protected(name):
    p=Path(name)
    return (p.name in ('package.json','package-lock.json','npm-shrinkwrap.json') or
            p.name.startswith(('tsconfig','vitest.config','vitest.base','biome.')) or
            name.startswith('scripts/') or '/scripts/' in name or
            name.startswith('packages/ai/src/models.generated') or
            '/model-data/' in name or name.startswith('packages/ai/src/providers/data/') or
            name.startswith('packages/ai/src/image-models.generated'))


def prepare(pins):
    # The pins and the crash-injection supervisor are specific to the canonical image:
    # dependencies_sha256 covers the amd64 node_modules (native addons differ per
    # architecture) and process_supervisor.py uses Linux/amd64 syscall numbers. Say so,
    # instead of reporting an unsupported host as a tampered dependency tree.
    machine = os.uname().machine
    if sys.platform != 'linux' or machine not in ('x86_64', 'amd64'):
        raise ValueError(f'Unsupported verifier platform {sys.platform}/{machine}: this task verifies on linux/amd64 only')
    if git('rev-parse',BASE).decode().strip()!=BASE: raise ValueError('Base object unavailable')
    if dependency_digest()!=pins['dependencies_sha256']: raise ValueError('Installed dependencies were modified')
    tracked=[part.decode() for part in git('ls-tree','-rz','--name-only',BASE).split(b'\0') if part]
    for name in tracked:
        if not protected(name): continue
        path=PI/name
        if path.is_symlink() or not path.is_file() or path.read_bytes()!=git('show',BASE+':'+name):
            raise ValueError('Protected dependency/build input changed: '+name)
    # Rehydrate pinned regression fixtures, including the public-API adaptation
    # below for legacy TUI session stubs. All original assertions remain intact.
    # Candidate-added tests remain available for development but do not select
    # or replace the regression inventory used for scoring.
    original=[]
    for name in tracked:
        if not name.startswith('packages/coding-agent/test/'): continue
        path=PI/name
        for parent in path.parents:
            if parent==PI: break
            if parent.is_symlink(): raise ValueError('Symlink in test fixture path')
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.is_symlink(): path.unlink()
        contents = git('show',BASE+':'+name)
        # Legacy TUI tests call a private helper on partial session receivers.
        # Supply the task-specified disabled-session API without changing their
        # event ordering, identity checks, assertions or testcase inventory.
        if name == 'packages/coding-agent/test/suite/regressions/5943-session-start-notify.test.ts':
            text = contents.decode()
            assert text.count('type RebindContext = {') == 1
            assert text.count('const context: RebindContext = {') == 3
            text = text.replace('type RebindContext = {', 'type RebindContext = {\n\tsession: { getRollbackState: () => { enabled: false; status: "ready" } };')
            text = text.replace('const context: RebindContext = {', 'const context: RebindContext = {\n\t\t\t\tsession: { getRollbackState: () => ({ enabled: false, status: "ready" }) },')
            contents = text.encode()
        elif name == 'packages/coding-agent/test/suite/regressions/startup-session-rebind-duplicate-subscription.test.ts':
            text = contents.decode()
            assert text.count('const startupSession = {};') == 1 and text.count('const replacementSession = {};') == 1
            text = text.replace('const startupSession = {};', 'const startupSession = { getRollbackState: () => ({ enabled: false, status: "ready" }) };')
            text = text.replace('const replacementSession = {};', 'const replacementSession = { getRollbackState: () => ({ enabled: false, status: "ready" }) };')
            contents = text.encode()
        elif name == 'packages/coding-agent/test/interactive-mode-startup-input.test.ts':
            text = contents.decode()
            assert text.count('\t\tisCompacting: boolean;') == 1
            assert text.count('\t\t\tisCompacting: false,') == 1
            text = text.replace('\t\tisCompacting: boolean;', '\t\tgetRollbackState: () => { enabled: false; status: "ready" };\n\t\tisCompacting: boolean;')
            text = text.replace('\t\t\tisCompacting: false,', '\t\t\tgetRollbackState: () => ({ enabled: false, status: "ready" }),\n\t\t\tisCompacting: false,')
            contents = text.encode()
        path.write_bytes(contents)
        if name.endswith(('.test.ts','.test.js','.test.mjs')):
            original.append(name.removeprefix('packages/coding-agent/'))
    return original


def change_owner(root,uid,gid):
    for directory, dirs, files in os.walk(root,followlinks=False):
        os.chown(directory,uid,gid)
        for name in dirs+files:
            path=Path(directory)/name
            os.chown(path,uid,gid,follow_symlinks=False)


def drop():
    # Build artifacts are later owned by the coordinator but must remain
    # readable by the independent unprivileged runtime workers.
    os.umask(0o022)
    os.setgroups([]); os.setgid(GID); os.setuid(UID)


def public_cache_umask():
    # Vitest's coordinator emits transform-cache modules read by low-privilege
    # workers. The scoring parent and its private logs keep their original mask.
    os.umask(0o022)


def run(argv,log,*,cwd=PI,env=None,low=False,timeout=1000):
    with (LOG/log).open('wb') as stream:
        try:
            return subprocess.run(argv,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT,
                                  preexec_fn=drop if low else public_cache_umask,timeout=timeout).returncode
        except subprocess.TimeoutExpired: return 124


def main():
    if os.getuid()!=0: raise SystemExit('Root verifier coordinator required')
    LOG.mkdir(parents=True,exist_ok=True)
    if LOG.is_symlink(): raise SystemExit('Unsafe log directory')
    change_owner(LOG,0,0)
    for directory,dirs,files in os.walk(LOG):
        os.chmod(directory,0o700)
        for name in files:
            path=Path(directory)/name
            if path.is_symlink(): path.unlink()
            else: os.chmod(path,0o600)
    (LOG/'reward.txt').write_text('0\n')
    report={'reward':0}
    env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/tmp/pi-rollback-build-home',
         'PI_OFFLINE':'1','PI_TELEMETRY':'0','PI_NO_LOCAL_LLM':'1','CI':'1','JITI_FS_CACHE':'false'}
    try:
        pins=json.loads((HERE/'baseline-pins.json').read_text())
        baseline=outcomes(Path('/opt/pi-baseline/coding-agent-junit.xml'))
        if digest(baseline)!=pins['outcomes_sha256']: raise ValueError('Base regression identity changed')
        original=prepare(pins)
        change_owner(PI,UID,GID)
        report['build_exit_code']=run(['npm','run','build:offline'],'build.log',env=env,low=True,timeout=900)
        if report['build_exit_code']: raise ValueError('Candidate did not build offline')
        prepare(pins)
        # Candidate code cannot overwrite tests, grading output, dependencies or
        # another candidate's source during the observation phase.
        change_owner(PI,0,0)
        for directory,dirs,files in os.walk(PI,followlinks=False):
            os.chmod(directory,stat.S_IMODE(os.stat(directory).st_mode)&~0o022)
            for name in files:
                p=Path(directory)/name
                if not p.is_symlink(): os.chmod(p,stat.S_IMODE(p.stat().st_mode)&~0o022)
        package=PI/'packages/coding-agent'
        os.chmod(package,0o1777)
        for cache in (package/'node_modules/.vite',package/'node_modules/.vite-temp'):
            if cache.exists(): shutil.rmtree(cache)
            cache.mkdir(parents=True,exist_ok=True)
        regression_env=dict(env,NODE_OPTIONS='--require='+str(HERE/'drop_worker.cjs'))
        report['regression_exit_code']=run(['node','../../node_modules/vitest/vitest.mjs','run','--config',str(package/'vitest.config.ts'),
             '--pool=forks','--retry','2','--maxWorkers=4','--reporter=junit','--outputFile='+str(LOG/'pass-to-pass-junit.xml'),*original],
             'pass-to-pass.log',cwd=package,env=regression_env,timeout=900)
        current=outcomes(LOG/'pass-to-pass-junit.xml')
        timestamp_failures=known_timestamp_failures(LOG/'pass-to-pass-junit.xml', pins)
        regressions=[key for key,status in baseline.items() if
                     (status=='passed' and current.get(key)!='passed' and key not in timestamp_failures) or
                     (status=='skipped' and current.get(key)!='skipped') or
                     (status=='failed' and current.get(key) not in ('failed','passed'))]
        comparison={'baseline_cases':len(baseline),'candidate_cases':len(current),
                    'missing':sorted(set(baseline)-set(current)),'extra':sorted(set(current)-set(baseline)),
                    'regressions':sorted(regressions)}
        comparison['accepted_timestamp_failures']=timestamp_failures
        comparison['passed']=not any(comparison[key] for key in ('missing','extra','regressions'))
        (LOG/'pass-to-pass-summary.json').write_text(json.dumps(comparison,indent=2)+'\n')
        report['regression_passed']=comparison['passed']
        # Keep the original test and full inventory. Independently exercise its
        # coalesced-reader/cancellation contract with a guaranteed file revision
        # change, so the narrow Base timestamp tolerance cannot mask that behavior.
        stable=package/'test/verifier-stable-auth-reload.test.ts'
        if stable.exists() or stable.is_symlink(): stable.unlink()
        stable.write_bytes((HERE/'stable_auth_reload.test.ts').read_bytes())
        stable.chmod(0o644)
        try:
            report['stable_auth_exit_code']=run(['node','../../node_modules/vitest/vitest.mjs','run','--config',str(package/'vitest.config.ts'),
                '--pool=forks','--maxWorkers=1','--reporter=junit','--outputFile='+str(LOG/'stable-auth-junit.xml'),str(stable)],
                'stable-auth.log',cwd=package,env=regression_env,timeout=120)
            stable_results=outcomes(LOG/'stable-auth-junit.xml')
            report['stable_auth_passed']=report['stable_auth_exit_code']==0 and len(stable_results)==1 and all(value=='passed' for value in stable_results.values())
        finally:
            stable.unlink(missing_ok=True)
        report['behavior_exit_code']=run(['python3',str(HERE/'verify.py'),'--output-dir',str(LOG/'behavior')],
                                         'behavior.log',env=env,timeout=1600)
        # This parent is independent of candidate Node processes. A candidate
        # process exiting zero cannot create any of these case observations.
        from verify import CASE_IDS
        behavior=json.loads((LOG/'behavior/behavior-results.json').read_text())
        ids=[item['id'] for item in behavior['results']]
        report['behavior_complete']=ids==CASE_IDS and behavior['expected_cases']==CASE_IDS
        report['behavior_passed']=report['behavior_complete'] and all(item['passed'] is True for item in behavior['results'])
        report['reward']=int(report['regression_passed'] and report['stable_auth_passed'] and report['behavior_passed'] and report['behavior_exit_code']==0)
    except Exception as error:
        report['error']=str(error)
    (LOG/'verifier-summary.json').write_text(json.dumps(report,indent=2)+'\n')
    (LOG/'reward.json').write_text(json.dumps({'reward': report['reward']})+'\n')
    (LOG/'reward.txt').write_text(str(report['reward'])+'\n')
    # Harbor reads mounted output as the host user after verification returns.
    # Publish read-only diagnostics only after all observations are complete;
    # candidate workers never receive write access to rewards or reports.
    for directory,dirs,files in os.walk(LOG):
        os.chmod(directory,0o755)
        for name in files:
            path=Path(directory)/name
            if not path.is_symlink(): os.chmod(path,0o644)
    print(json.dumps(report))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
