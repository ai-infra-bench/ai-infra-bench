#!/usr/bin/python3
"""Root-only scoring owner; untrusted Pi runs in worker_exec.py's UID."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


class ScoringError(RuntimeError):
    pass


def score_completed_results(summary, expected_cases, returncode):
    """Only a complete, observed behavioral decision can produce a reward."""
    if not isinstance(summary, dict) or not isinstance(summary.get('results'), list):
        raise ScoringError('Verifier did not produce a result list')
    results = summary['results']
    if ([result.get('name') for result in results] != list(expected_cases)
            or summary.get('case_count') != len(expected_cases)
            or any(type(result.get('passed')) is not bool for result in results)):
        raise ScoringError('Verifier result set is incomplete or malformed')
    infrastructure = [str(error) for result in results
                      for error in result.get('infrastructure_errors', [])]
    if infrastructure:
        raise ScoringError('; '.join(infrastructure))
    passed = sum(result['passed'] for result in results)
    if summary.get('passed') != passed or returncode not in (0, 1):
        raise ScoringError('Verifier completion disagrees with its result summary')
    if passed == len(expected_cases):
        if returncode != 0:
            raise ScoringError('Verifier failed after reporting all cases passed')
        if any(result.get('runtime_observation', {}).get('passed') is not True for result in results):
            raise ScoringError('Successful cases lack completed native execution observations')
        return 1
    return 0

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
    # Remove any stale/candidate-supplied reward before scoring.
    for name in ['reward.txt', 'reward.json']:
        (LOGS / name).unlink(missing_ok=True)
    success = False
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
            path.chmod(0o644 if path.name in ['fixture.ts', 'worker_exec.py', 'trusted_faux.mjs'] else 0o600)
        sys.path.insert(0, str(TESTS))
        from runtime_observer import preflight_harness
        preflight_harness(TESTS)
        reward(0)
        output = LOGS / ('text-behavior')
        # Do not reuse a tree supplied by the solver or a previous invocation.
        if output.exists() or output.is_symlink():
            raise RuntimeError('Refusing existing behavior output')
        # -I excludes cwd, PYTHONPATH, and user site packages. This explicitly
        # adds only the sealed harness directory for its trusted imports.
        command = ['/usr/bin/python3', '-I', '-c',
                   "import sys; sys.dont_write_bytecode=True; sys.path.insert(0, '/tests'); import verify; raise SystemExit(verify.main())",
                   '--repo', '/workspace/pi', '--output', str(output)]
        completed = subprocess.run(command, cwd='/', env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8'})
        spec = importlib.util.spec_from_file_location('trusted_verify', TESTS / 'verify.py')
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(TESTS))
        spec.loader.exec_module(module)
        summary = json.loads((output / 'summary.json').read_text())
        success = bool(score_completed_results(summary, module.CASES, completed.returncode))
        status.update(status='scored', feature_score=int(success))
    except ScoringError as exc:
        status.update(status='scoring_error', feature_score=None, reason=str(exc))
    except Exception as exc:
        status.update(status='scoring_error', feature_score=None,
                      reason=f'{type(exc).__name__}: {exc}')
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
