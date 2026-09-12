"""Run the unmodified grading entrypoint in fresh, offline CPU containers."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

TASK = Path(__file__).resolve().parents[1]
IMAGE = os.environ.get('TASK_IMAGE', 'ai-infra-bench/vllm-request-lifecycle-leak:base-e94ec597334d-avx2')
OUT = Path(os.environ.get('MATRIX_OUT', '/tmp/pr55-hardening-matrix')).resolve()
CASES = {'base': None, 'oracle': TASK / 'solution/oracle.patch'}
for case in json.loads((TASK / 'validation/ci-cases.json').read_text())['cases']:
    CASES[case['name']] = TASK / 'validation' / case['patch']
if os.environ.get('MATRIX_CASES'):
    CASES = {name: CASES[name] for name in os.environ['MATRIX_CASES'].split(',')}

def command(args, timeout=360):
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=timeout)
    return result

def run(item):
    name, patch = item
    start = time.monotonic()
    directory = OUT / name
    directory.mkdir(parents=True, exist_ok=True)
    logs = directory / 'logs'
    logs.mkdir(exist_ok=True)
    container = f'pr55-hardening-{name}-{os.getpid()}'
    record = {'case': name, 'image': IMAGE, 'patch_sha256':
              hashlib.sha256(patch.read_bytes()).hexdigest() if patch else None}
    try:
        args = ['docker', 'run', '-d', '--name', container, '--network', 'none',
            '--cpus', '4', '--memory', '16g', '--ulimit', 'core=0', '--user', 'root',
            '--entrypoint', 'bash', '-v', f'{TASK / "tests"}:/tests:ro',
            '-v', f'{logs}:/logs/verifier']
        if patch:
            args += ['-v', f'{patch}:/candidate.patch:ro']
        result = command(args + [IMAGE, '-c', 'sleep infinity'])
        assert result.returncode == 0, result.stdout
        if patch:
            result = command(['docker', 'exec', '--user', 'agent', container,
                'git', 'apply', '/candidate.patch'])
            assert result.returncode == 0, result.stdout
        result = command(['docker', 'exec', container, 'bash', '/tests/test.sh'])
        (directory / 'entrypoint.log').write_text(result.stdout)
        record['exit_code'] = result.returncode
        record['reward'] = int((logs / 'reward.txt').read_text())
    except Exception as exc:
        record['error'] = str(exc)
    finally:
        command(['docker', 'rm', '-f', container])
    record['elapsed_sec'] = round(time.monotonic() - start, 2)
    (directory / 'result.json').write_text(json.dumps(record, indent=2))
    print(json.dumps(record), flush=True)
    return record

if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, CASES.items()))
    (OUT / 'results.json').write_text(json.dumps(results, indent=2))
