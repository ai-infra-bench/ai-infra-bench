"""Populate ordinary developer caches without changing the Base checkout."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

LOCK = Path('/tmp/dev-tools/lock')
HOME = Path('/home/agent')
REPO = Path('/workspace/repo')
PYTHON = str(REPO / '.venv/bin/python')


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def download(item, destination):
    for attempt in range(3):
        try:
            run('curl', '--fail', '--location', '--retry', '3', '--retry-all-errors',
                '--connect-timeout', '30', '--max-time', '300', '--continue-at', '-',
                '--output', str(destination), item['url'])
            assert hashlib.sha256(destination.read_bytes()).hexdigest() == item['sha256']
            return
        except Exception:
            if attempt == 2:
                raise


def prepare():
    chains = json.loads((LOCK / 'toolchains.json').read_text())
    mirror = Path('/tmp/node-mirror')
    node = chains['node']
    version = node['version']
    release = mirror / f'v{version}'
    release.mkdir(parents=True)
    download(node, release / f'node-v{version}-linux-x64.tar.gz')
    (mirror / 'index.json').write_text(json.dumps([
        {'version': f'v{version}', 'lts': True, 'files': ['linux-x64']},
    ]))
    # Resolve the upstream `lts` selector against a single pinned release. The
    # upstream config and pre-commit's cache key remain unchanged.
    (HOME / '.nodeenvrc').write_text(f'[nodeenv]\nmirror = {mirror.as_uri()}\n')
    archive = Path('/tmp/go.tar.gz')
    download(chains['go'], archive)
    with tarfile.open(archive) as src:
        src.extractall('/usr/local', filter='data')
    archive.unlink()
    run('chown', '-R', 'agent:agent', str(HOME / '.nodeenvrc'))
    env = dict(os.environ, HOME=str(HOME), PATH='/usr/local/go/bin:' + os.environ['PATH'],
               PIP_CONSTRAINT=str(LOCK / 'hook-constraints.txt'),
               npm_config_maxsockets='3', npm_config_fetch_retries='5',
               GOTOOLCHAIN='local')
    run('runuser', '-u', 'agent', '--', PYTHON, __file__, 'hooks', env=env, cwd=REPO)
    (HOME / '.nodeenvrc').unlink()
    shutil.rmtree(mirror)


def hooks():
    from pre_commit.clientlib import load_config
    from pre_commit.repository import all_hooks, install_hook_envs
    from pre_commit.store import Store

    store = Store()
    hooks = all_hooks(load_config('.pre-commit-config.yaml'), store)
    expected = json.loads((LOCK / 'hook-revisions.json').read_text())
    for hook in hooks:
        if hook.src == 'local':
            continue
        prefix = Path(hook.prefix.prefix_dir)
        actual = subprocess.check_output(['git', '-C', str(prefix), 'rev-parse', 'HEAD'], text=True).strip()
        assert actual == expected[hook.src], (hook.src, actual)
        if hook.language == 'node':
            shutil.copyfile(LOCK / 'markdownlint-npm-shrinkwrap.json', prefix / 'npm-shrinkwrap.json')
    for attempt in range(3):
        try:
            install_hook_envs(hooks, store)
            break
        except Exception:
            if attempt == 2:
                raise
    run(str(REPO / '.venv/bin/pre-commit'), 'install')


if __name__ == '__main__':
    import sys
    hooks() if sys.argv[1:] == ['hooks'] else prepare()
