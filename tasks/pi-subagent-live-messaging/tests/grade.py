#!/usr/bin/python3
"""Root-only scoring owner; untrusted Pi runs in worker_exec.py's UID."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

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


def publish_status(status):
    fd, name = tempfile.mkstemp(prefix='.status-', dir=LOGS)
    with os.fdopen(fd, 'w') as stream:
        json.dump(status, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(name, LOGS / 'grading-status.json')


def publish_results():
    # Harbor collects as a different host UID. Reveal completed artifacts only
    # after grading; they remain root-owned and never writable by candidates.
    output = LOGS / 'text-behavior'
    paths = [p for p in [LOGS / 'reward.txt', LOGS / 'reward.json',
                         LOGS / 'grading-status.json'] if p.exists()]
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
    # A missing reviewed interface is unscored, not a failed implementation.
    # Remove any stale/candidate-supplied entry before selecting an adapter.
    for name in ['reward.txt', 'reward.json']:
        (LOGS / name).unlink(missing_ok=True)
    success = False
    integration_needed = False
    status = {'status': 'scoring_error', 'feature_score': None}
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
        sys.path.insert(0, str(TESTS))
        from profile import IntegrationNeeded, validate_profile
        try:
            binding, scenario, selected = validate_profile(Path('/workspace/pi'), TESTS)
        except IntegrationNeeded as exc:
            integration_needed = True
            status = {'status': 'integration_needed', 'feature_score': None,
                      'reason': str(exc)}
            return 2
        status['profile_id'] = selected['profile_id']
        status['workspace'] = selected['workspace']
        reward(0)
        output = LOGS / ('text-behavior')
        # Do not reuse a tree supplied by the solver or a previous invocation.
        if output.exists() or output.is_symlink():
            raise RuntimeError('Refusing existing behavior output')
        # -I excludes cwd, PYTHONPATH, and user site packages. This explicitly
        # adds only the sealed harness directory for its trusted binding import.
        command = ['/usr/bin/python3', '-I', '-c',
                   "import sys; sys.dont_write_bytecode=True; sys.path.insert(0, '/tests'); import verify; raise SystemExit(verify.main())",
                   '--repo', '/workspace/pi', '--output', str(output),
                   '--binding', str(binding), '--scenario', str(scenario)]
        completed = subprocess.run(command, cwd='/', env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8'})
        spec = importlib.util.spec_from_file_location('trusted_verify', TESTS / 'verify.py')
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(TESTS))
        spec.loader.exec_module(module)
        summary = json.loads((output / 'summary.json').read_text())
        if summary.get('status') == 'integration_needed':
            integration_needed = True
            status.update(status='integration_needed', feature_score=None,
                          reason='Reviewed scenario could not execute; see case evidence')
            return 2
        results = summary['results']
        success = (completed.returncode == 0
                   and [r['name'] for r in results] == module.CASES
                   and all(r['passed'] is True for r in results)
                   and summary['case_count'] == summary['passed'] == len(module.CASES))
        status.update(status='scored', feature_score=int(success))
    finally:
        # Infrastructure failure is unscored too. Only a completed scoring
        # decision may leave a reward for Harbor; remove the provisional zero
        # when the verifier failed before producing a usable summary.
        if status['status'] != 'scored':
            for name in ['reward.txt', 'reward.json']:
                (LOGS / name).unlink(missing_ok=True)
        else:
            reward(int(success))
        publish_status(status)
        publish_results()
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
