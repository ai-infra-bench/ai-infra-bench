#!/usr/bin/env python3
"""Prepare an explicitly reviewed profile and run one Docker/Harbor replay.

Requires Python 3.11+, local Docker and Harbor. No model or Ray is used.
--submission is a complete patch against Base unless --after-oracle is explicit.
--dry-run validates inputs and prints the plan without Docker, Harbor or writes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import tomllib


def hashes(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if '__pycache__' in path.parts:
            continue
        if path.is_symlink():
            raise ValueError('Task inputs must not be symlinks: ' + str(path))
        if path.is_file():
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def ownership_evidence(info, jobs):
    """Prove ownership from an isolated run path, never from a guessed name."""
    jobs = jobs.resolve()
    labels = info.get('Config', {}).get('Labels') or {}
    project = labels.get('com.docker.compose.project')
    if not project:
        return None
    trials = [p.resolve() for p in jobs.glob('*/*')
              if p.is_dir() and not p.is_symlink() and (p / 'config.json').is_file()]
    candidates = [('compose_working_dir', labels.get('com.docker.compose.project.working_dir'))]
    candidates.extend(('bind_mount', item.get('Source')) for item in info.get('Mounts', [])
                      if item.get('Type') == 'bind')
    proof = []
    for kind, value in candidates:
        if not isinstance(value, str) or not Path(value).is_absolute():
            continue
        location = Path(value).resolve()
        # A unique run-owned working directory suffices. Bind mounts require a
        # specific recorded trial to avoid identifying shared task/cache mounts.
        if kind == 'compose_working_dir' and location.is_relative_to(jobs):
            proof.append({'kind': kind, 'path': str(location)})
        elif kind == 'bind_mount':
            for trial in trials:
                if location.is_relative_to(trial):
                    proof.append({'kind': kind, 'path': str(location), 'trial': trial.name,
                                  'config_sha256': hashlib.sha256((trial / 'config.json').read_bytes()).hexdigest()})
                    break
    if not proof:
        return None
    host = info.get('HostConfig') or {}
    return {'id': info['Id'], 'project': project, 'ownership': proof,
            'runtime': {'network_mode': host.get('NetworkMode'), 'memory': host.get('Memory'),
                        'nano_cpus': host.get('NanoCpus'), 'cpu_quota': host.get('CpuQuota'),
                        'cpu_period': host.get('CpuPeriod')}}


def harbor_command(args, prepared):
    command = [args.harbor, 'run', '--path', str(prepared), '--agent', 'nop' if args.base else 'oracle',
               '--env', 'docker', '--jobs-dir', str(args.output / 'jobs'), '--job-name', 'reviewed-replay',
               '--n-attempts', '1', '--n-concurrent', '1', '--max-retries', '0', '--yes']
    for flag, value in [('--cpus', args.cpus), ('--memory', args.memory), ('--override-cpus', args.override_cpus)]:
        if value is not None:
            command.extend([flag, str(value)])
    if args.delete:
        command.append('--delete')
    return command


def preparation_command(args, config):
    command = ['docker', 'run', '-d', '--network', 'none', '--user', '0']
    if args.cpus == 'limit':
        command.extend(['--cpus', str(args.override_cpus or config['environment']['cpus'])])
    if args.memory == 'limit':
        command.extend(['--memory', str(config['environment']['memory_mb']) + 'm'])
    return command + ['--entrypoint', 'sleep', args.image, 'infinity']


def inputs(args):
    args.task = args.task.resolve(strict=True)
    args.output = args.output.absolute()
    if args.output.exists():
        raise ValueError('Use a new output directory; existing runs are never overwritten')
    if args.output.resolve() == args.task or args.task in args.output.resolve().parents:
        raise ValueError('Run output must be outside the source task')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', args.image):
        raise ValueError('--image must be an immutable local sha256 image ID')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,80}', args.profile_id):
        raise ValueError('Invalid --profile-id')
    if args.after_oracle and args.submission is None:
        raise ValueError('--after-oracle requires --submission')
    config = tomllib.loads((args.task / 'task.toml').read_text())
    if config['environment']['workdir'] != '/workspace/pi':
        raise ValueError('This task-specific runner requires /workspace/pi')
    agent_user = config['agent'].get('user')
    if not agent_user or agent_user in ('root', '0', 0):
        raise ValueError('Task must specify an unprivileged agent user')
    frozen = hashes(args.task)
    required = ['tests/profile.py', 'tests/grade.py', 'tests/test.sh',
                'validation/tools/prepare_profile.py']
    if not all(name in frozen for name in required):
        raise ValueError('Incomplete task/profile tool inputs')
    files = {}
    for name in ['binding', 'scenario', 'review_evidence'] + (['submission'] if args.submission else []):
        path = getattr(args, name)
        if path.is_symlink() or not path.is_file():
            raise ValueError('Input must be an explicit regular file: ' + str(path))
        content = path.read_bytes()
        files[name] = content
    review = json.loads(files['review_evidence'])
    if not isinstance(review, dict) or not review:
        raise ValueError('Nonempty review evidence object required')
    if any(name in frozen for name in ['tests/profile.json', 'tests/interface_binding.py', 'tests/scenario_binding.py']):
        raise ValueError('Source task already contains a generated profile; use its clean reviewed revision')
    return config, files, {
        'image': args.image, 'source_task': str(args.task), 'output': str(args.output),
        'kind': 'submission' if args.submission else ('oracle' if args.oracle else 'base'),
        'apply_after': 'oracle' if args.after_oracle else 'base',
        'profile_id': args.profile_id, 'agent_user': agent_user,
        'source_sha256': frozen,
        'input_sha256': {key: hashlib.sha256(data).hexdigest() for key, data in files.items()},
        'harbor_argv': harbor_command(args, args.output / 'task'),
        'preparation_argv': preparation_command(args, config),
        'artifact_policy': 'omit top-level workspace archive' if args.no_artifacts else 'preserve task artifacts',
        'stages': ['freeze inputs', 'materialize in pinned offline Docker image as agent user',
                   'prepare explicit profile as curator', 'export profile and remove preparation container',
                   'single Harbor replay from same image and materialization inputs'],
        'limitations': ['Patch replay does not restore arbitrary ignored/untracked filesystem changes.',
                        'Preparation is not a feature pass; Harbor must complete and collect matching rewards.',
                        'Generic CI uses this runner only through an explicit reviewed_replay case catalog.'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--task', type=Path, required=True)
    parser.add_argument('--image', required=True, help='Immutable sha256 Docker image ID, already available locally')
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--base', action='store_true')
    choice.add_argument('--oracle', action='store_true')
    choice.add_argument('--submission', type=Path, help='Full Base-relative patch; not a tar archive')
    parser.add_argument('--after-oracle', action='store_true', help='Apply submission patch after the explicit task Oracle')
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--scenario', type=Path, required=True)
    parser.add_argument('--review-evidence', type=Path, required=True)
    parser.add_argument('--profile-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--harbor', default='harbor', help='Harbor executable (single path, not a shell command)')
    parser.add_argument('--timeout', type=int, default=10800, help='Harbor command wall-clock timeout in seconds')
    parser.add_argument('--cpus', choices=('limit', 'ignore'), help='Explicit Harbor CPU mode; limit also applies to preparation')
    parser.add_argument('--memory', choices=('limit', 'ignore'), help='Explicit Harbor memory mode; limit also applies to preparation')
    parser.add_argument('--override-cpus', type=int, help='Harbor CPU count override, e.g. public CPU CI uses 4')
    parser.add_argument('--no-artifacts', action='store_true', help='Omit top-level workspace archives in disposable task only')
    parser.add_argument('--delete', action='store_true', help='Forward Harbor environment cleanup flag')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        config, files, plan = inputs(args)
        if args.timeout <= 0:
            raise ValueError('--timeout must be positive')
        if args.override_cpus is not None and args.override_cpus <= 0:
            raise ValueError('--override-cpus must be positive')
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return 0

    args.output.mkdir(parents=True, exist_ok=False)
    record = {'plan': plan, 'status': 'preparing', 'started_at': time.time(), 'commands': []}
    container = None
    exit_code = 2
    prepared = args.output / 'task'
    request = args.output / 'inputs'

    def write_record():
        (args.output / 'replay.json').write_text(json.dumps(record, indent=2) + '\n')

    def execute(argv, stage, timeout=120, capture=False, cleanup=False):
        if not cleanup and (args.output / 'STOP_REQUESTED').exists():
            raise InterruptedError('STOP_REQUESTED')
        log = args.output / (stage + '.log')
        event = {'argv': argv, 'stage': stage, 'started_at': time.time()}
        record['commands'].append(event)
        write_record()
        with log.open('ab') as stream:
            proc = subprocess.Popen(argv, stdout=subprocess.PIPE if capture else stream,
                                    stderr=stream, start_new_session=True)
            try:
                while True:
                    try:
                        output, _ = proc.communicate(timeout=1)
                        break
                    except subprocess.TimeoutExpired:
                        if time.time() - event['started_at'] > timeout:
                            raise TimeoutError('Command timed out: ' + stage)
                        if not cleanup and (args.output / 'STOP_REQUESTED').exists():
                            raise InterruptedError('STOP_REQUESTED')
            except BaseException:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.communicate(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.communicate()
                raise
        event.update(exit_code=proc.returncode, finished_at=time.time())
        write_record()
        if proc.returncode:
            raise RuntimeError('Command failed; see ' + str(log))
        return output.decode().strip() if capture else None

    def stop(signum, frame):
        raise InterruptedError('Received signal ' + str(signum))

    def cleanup_harbor_containers():
        audit = {'removed': [], 'unproven_compose_containers': 0,
                 'policy': 'Only exact container IDs proved by own jobs working-dir or own trial bind mount; no name inference or prune.'}
        record['harbor_cleanup'] = audit
        raw = execute(['docker', 'ps', '-aq', '--filter', 'label=com.docker.compose.project'],
                      'harbor-cleanup', capture=True, cleanup=True)
        ids = raw.split()
        for identity in ids:
            if not re.fullmatch(r'[0-9a-f]{12,64}', identity):
                raise RuntimeError('Unexpected Docker container ID during cleanup')
            try:
                detail = json.loads(execute(['docker', 'inspect', identity], 'harbor-cleanup',
                                            capture=True, cleanup=True))[0]
            except RuntimeError:
                # Another job may have independently removed its own container.
                audit.setdefault('inspect_errors', []).append(identity)
                continue
            proof = ownership_evidence(detail, args.output / 'jobs')
            if proof is None:
                audit['unproven_compose_containers'] += 1
                continue
            execute(['docker', 'rm', '-f', proof['id']], 'harbor-cleanup', cleanup=True)
            audit['removed'].append(proof)
        audit['scope'] = 'All containers whose ownership was proven were removed; containers without proof were left untouched. This is not a global absence certificate.'

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        shutil.copytree(args.task, prepared, ignore=shutil.ignore_patterns('__pycache__'))
        if hashes(prepared) != plan['source_sha256']:
            raise ValueError('Source task changed during copy')
        request.mkdir()
        for name, content in files.items():
            (request / name).write_bytes(content)
        record['copied_input_sha256'] = hashes(request)
        if record['copied_input_sha256'] != plan['input_sha256']:
            raise ValueError('Copied curator inputs do not match frozen bytes')
        source_toml = (prepared / 'task.toml').read_text()
        if config['environment'].get('docker_image') is not None:
            raise ValueError('Source task must not already have an injected docker_image')
        if source_toml.count('[environment]\n') != 1:
            raise ValueError('Expected normalized task.toml environment section')
        replay_toml = source_toml.replace('[environment]\n', '[environment]\ndocker_image = ' + json.dumps(args.image) + '\n')
        expected = dict(config)
        expected['environment'] = dict(config['environment'], docker_image=args.image)
        if args.no_artifacts and 'artifacts' in expected:
            replay_toml, count = re.subn(r'(?m)^artifacts\s*=\s*\[[^\n]*\]', 'artifacts = []', replay_toml, count=1)
            if count != 1:
                raise ValueError('Expected normalized top-level artifacts field')
            expected['artifacts'] = []
        if tomllib.loads(replay_toml) != expected:
            raise ValueError('Task image injection changed unrelated config')
        (prepared / 'task.toml').write_text(replay_toml)
        solution = prepared / 'solution'
        if args.submission:
            if args.after_oracle:
                for reserved in ['reviewed-oracle-solve.sh', 'reviewed-submission.patch']:
                    if (solution / reserved).exists():
                        raise ValueError('Oracle solution has reserved replay filename: ' + reserved)
                (solution / 'solve.sh').rename(solution / 'reviewed-oracle-solve.sh')
            else:
                shutil.rmtree(solution)
                solution.mkdir()
            (solution / 'reviewed-submission.patch').write_bytes(files['submission'])
            script = '#!/bin/bash\nset -euo pipefail\ncd /workspace/pi\n'
            if args.after_oracle:
                script += 'bash /solution/reviewed-oracle-solve.sh\n'
            script += 'git apply --check /solution/reviewed-submission.patch\ngit apply /solution/reviewed-submission.patch\n'
            (solution / 'solve.sh').write_text(script)
            (solution / 'solve.sh').chmod(0o755)
        inspected = execute(['docker', 'image', 'inspect', args.image, '--format', '{{.Id}}'], 'runtime', capture=True)
        if inspected != args.image:
            raise ValueError('Docker image identity mismatch')
        record['harbor_version'] = execute([args.harbor, '--version'], 'runtime', capture=True)
        container = execute(preparation_command(args, config), 'prepare', capture=True)
        record['preparation_container'] = container
        execute(['docker', 'cp', str(prepared), container + ':/curator-task'], 'prepare')
        execute(['docker', 'cp', str(solution), container + ':/solution'], 'prepare')
        execute(['docker', 'cp', str(request), container + ':/curator-inputs'], 'prepare')
        if not args.base:
            execute(['docker', 'exec', '-u', str(config['agent']['user']), container,
                     'bash', '/solution/solve.sh'], 'materialize', timeout=300)
        execute(['docker', 'exec', '-u', '0', container, '/usr/bin/python3', '-I',
                 '/curator-task/validation/tools/prepare_profile.py', '--repo', '/workspace/pi',
                 '--tests', '/curator-task/tests', '--profile-id', args.profile_id,
                 '--interface', '/curator-inputs/binding', '--scenario', '/curator-inputs/scenario',
                 '--review-evidence', '/curator-inputs/review_evidence'], 'profile', timeout=1800)
        for name in ['profile.json', 'interface_binding.py', 'scenario_binding.py']:
            execute(['docker', 'exec', '-u', '0', container, 'chmod', '644', '/curator-task/tests/' + name], 'export')
            execute(['docker', 'cp', container + ':/curator-task/tests/' + name,
                     str(prepared / 'tests' / name)], 'export')
        record['profile'] = json.loads((prepared / 'tests/profile.json').read_text())
        record['prepared_sha256'] = hashes(prepared)
        execute(['docker', 'rm', '-f', container], 'cleanup', cleanup=True)
        container = None
        record['status'] = 'grading'
        write_record()
        job = 'reviewed-replay'
        execute(harbor_command(args, prepared), 'harbor', timeout=args.timeout)
        trial_files = list((args.output / 'jobs' / job).glob('*/result.json'))
        statuses = list((args.output / 'jobs' / job).glob('*/verifier/grading-status.json'))
        if len(trial_files) != 1 or len(statuses) != 1:
            raise RuntimeError('Expected exactly one collected trial and grading status')
        trial = json.loads(trial_files[0].read_text())
        grading = json.loads(statuses[0].read_text())
        record.update(trial_result=trial, grading_status=grading)
        if trial.get('exception_info') or grading.get('status') != 'scored':
            raise RuntimeError('Trial is unscored or errored; inspect grading status and Harbor evidence')
        collected_reward = (trial.get('verifier_result') or {}).get('rewards', {}).get('reward')
        if collected_reward not in (0, 1) or collected_reward != grading.get('feature_score'):
            raise RuntimeError('Collected Harbor reward does not match grading status')
        record.update(status='completed', reward=collected_reward)
        exit_code = 0
    except BaseException as exc:
        record.update(status='stopped' if isinstance(exc, (InterruptedError, KeyboardInterrupt)) else 'error',
                      error=type(exc).__name__ + ': ' + str(exc))
        print(record['error'], file=sys.stderr)
        exit_code = 2
    finally:
        if container:
            try:
                execute(['docker', 'rm', '-f', container], 'cleanup', cleanup=True)
            except BaseException as exc:
                record['cleanup_error'] = str(exc)
                exit_code = 2
        if record['status'] != 'completed' and (args.output / 'jobs').exists():
            try:
                cleanup_harbor_containers()
            except BaseException as exc:
                record['harbor_cleanup_error'] = str(exc)
                exit_code = 2
        provenance = {}
        for name, directory, expected_hashes in [
                ('copied_inputs', request, record.get('copied_input_sha256')),
                ('prepared_task', prepared, record.get('prepared_sha256'))]:
            if expected_hashes is None:
                provenance[name] = {'status': 'not_frozen_before_interruption'}
                continue
            try:
                actual = hashes(directory)
                matched = actual == expected_hashes
                provenance[name] = {'status': 'matched' if matched else 'changed', 'post_sha256': actual}
                if not matched:
                    record['status'] = 'error'
                    record.setdefault('provenance_errors', []).append(name + ' changed during replay')
                    exit_code = 2
            except BaseException as exc:
                provenance[name] = {'status': 'unreadable', 'error': str(exc)}
                record['status'] = 'error'
                exit_code = 2
        record['post_run_provenance'] = provenance
        record['finished_at'] = time.time()
        write_record()
        print(json.dumps({'status': record['status'], 'reward': record.get('reward'),
                          'record': str(args.output / 'replay.json')}))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
