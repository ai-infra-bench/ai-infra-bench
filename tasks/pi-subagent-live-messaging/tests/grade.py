#!/usr/bin/python3
"""Root-only scoring owner; untrusted Pi runs in worker_exec.py's UID."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

TESTS = Path('/tests')
LOGS = Path('/logs/verifier')


def protect_directory(path):
    # Refuse symlinks, including a preplanted output directory.
    path.mkdir(exist_ok=True)
    fd = os.open(path, os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fchown(fd, 0, 0)
        os.fchmod(fd, 0o700)
    finally:
        os.close(fd)


def reward(value):
    # Replacing the directory entry avoids following a preplanted reward symlink
    # or overwriting the target of a preplanted hard link.
    for filename, content in [('reward.txt', f'{value}\n'),
                              ('reward.json', json.dumps({'reward': value}) + '\n')]:
        fd, name = tempfile.mkstemp(prefix='.reward-', dir=LOGS)
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, LOGS / filename)


def publish_results():
    # Harbor collects as a different host UID. Reveal completed artifacts only
    # after grading; they remain root-owned and never writable by candidates.
    output = LOGS / 'text-behavior'
    paths = [LOGS / 'reward.txt', LOGS / 'reward.json']
    if output.exists() and not output.is_symlink():
        paths.extend(output.rglob('*'))
        paths.append(output)
    for path in paths:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fchmod(fd, 0o755 if path.is_dir() else 0o644)
        finally:
            os.close(fd)
    LOGS.chmod(0o755)


def main():
    assert os.geteuid() == 0, 'grader must own its privilege boundary'
    os.umask(0o077)
    protect_directory(Path('/logs'))
    protect_directory(LOGS)
    reward(0)
    success = False
    try:
        # The mounted harness is trusted; candidate workspace never enters the
        # Python import path. Pi only needs the fixture and privilege launcher.
        os.chown(TESTS, 0, 0)
        TESTS.chmod(0o755)
        for path in TESTS.iterdir():
            if path.is_symlink() or not path.is_file():
                raise RuntimeError(f'Unexpected harness entry: {path.name}')
            os.chown(path, 0, 0)
            path.chmod(0o644 if path.name in ['fixture.ts', 'worker_exec.py'] else 0o600)
        output = LOGS / ('text-behavior')
        # Do not reuse a tree supplied by the solver or a previous invocation.
        if output.exists() or output.is_symlink():
            raise RuntimeError('Refusing existing behavior output')
        # -I excludes cwd, PYTHONPATH, and user site packages. This explicitly
        # adds only the sealed harness directory for its trusted binding import.
        command = ['/usr/bin/python3', '-I', '-c',
                   "import sys; sys.path.insert(0, '/tests'); import verify; raise SystemExit(verify.main())",
                   '--repo', '/workspace/pi', '--output', str(output)]
        if (TESTS / 'interface_binding.py').is_file():
            command += ['--binding', str(TESTS / 'interface_binding.py')]
        if (TESTS / 'scenario_binding.py').is_file():
            command += ['--scenario', str(TESTS / 'scenario_binding.py')]
        completed = subprocess.run(command, cwd='/', env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8'})
        spec = importlib.util.spec_from_file_location('trusted_verify', TESTS / 'verify.py')
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(TESTS))
        spec.loader.exec_module(module)
        summary = json.loads((output / 'summary.json').read_text())
        results = summary['results']
        success = (completed.returncode == 0
                   and [r['name'] for r in results] == module.CASES
                   and all(r['passed'] is True for r in results)
                   and summary['case_count'] == summary['passed'] == len(module.CASES))
    finally:
        reward(int(success))
        publish_results()
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
