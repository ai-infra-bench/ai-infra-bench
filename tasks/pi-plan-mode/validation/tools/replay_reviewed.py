#!/usr/bin/env python3
"""Materialize a reviewed submission, bind its UI profile, replay via Harbor."""
import argparse
import json
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tomllib
import uuid


def run(*command):
    subprocess.run(list(map(str, command)), check=True)


def main():
    parser = argparse.ArgumentParser()
    for name in ('task', 'output', 'binding', 'scenario', 'review-evidence', 'submission'):
        parser.add_argument('--' + name, type=Path, required=name != 'submission')
    for name in ('image', 'profile-id', 'cpus', 'memory'):
        parser.add_argument('--' + name, required=True)
    for name in ('base', 'oracle', 'after-oracle', 'no-artifacts', 'delete'):
        parser.add_argument('--' + name, action='store_true')
    parser.add_argument('--override-cpus', type=int)
    args = parser.parse_args()
    if sum((args.base, args.oracle, args.submission is not None)) != 1:
        parser.error('Select exactly one of base, oracle or submission')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', args.image):
        parser.error('An immutable local Docker image ID is required')
    args.output.mkdir(parents=True, exist_ok=False)
    task = args.output / 'task'
    shutil.copytree(args.task, task)
    text = (task / 'task.toml').read_text()
    config = tomllib.loads(text)
    text = re.sub(r'(?m)^docker_image\s*=.*\n', '', text)
    text = text.replace('[environment]\n', '[environment]\ndocker_image = ' + json.dumps(args.image) + '\n', 1)
    if args.no_artifacts:
        text = re.sub(r'(?m)^artifacts\s*=.*$', 'artifacts = []', text, count=1)
    (task / 'task.toml').write_text(text)
    solution = task / 'solution'
    if args.submission:
        if args.after_oracle:
            (solution / 'solve.sh').rename(solution / 'oracle-solve.sh')
            prefix = 'bash /solution/oracle-solve.sh\n'
        else:
            shutil.rmtree(solution)
            solution.mkdir()
            prefix = ''
        shutil.copy2(args.submission, solution / 'reviewed.patch')
        (solution / 'solve.sh').write_text('#!/usr/bin/env bash\nset -euo pipefail\ncd /workspace/pi\n' + prefix + 'git apply --check /solution/reviewed.patch\ngit apply /solution/reviewed.patch\n')
    shutil.copy2(args.binding, task / 'tests/ui-actions.json')
    for name, source in [('review-evidence.json', args.review_evidence), ('scenario.json', args.scenario)]:
        shutil.copy2(source, args.output / name)
    container = 'pi-plan-profile-' + uuid.uuid4().hex
    try:
        run('docker', 'run', '-d', '--name', container, '--network', 'none', '--init',
            '--cpus', str(args.override_cpus or config['environment']['cpus']),
            '--memory', str(config['environment']['memory_mb']) + 'm', args.image, 'sleep', 'infinity')
        run('docker', 'cp', task / 'tests', container + ':/tests')
        if not args.base:
            run('docker', 'cp', solution, container + ':/solution')
            run('docker', 'exec', '--user', config['agent']['user'], container, 'bash', '/solution/solve.sh')
        for name in ('review-evidence.json', 'scenario.json'):
            run('docker', 'cp', args.output / name, container + ':/' + name)
        run('docker', 'exec', '--user', 'root', container, 'python3', '-I', '/tests/ui_profile.py', 'create',
            '--tests', '/tests', '--image', args.image, '--profile-id', args.profile_id,
            '--evidence', '/review-evidence.json', '--scenario', '/scenario.json')
        run('docker', 'cp', container + ':/tests/ui-profile.json', task / 'tests/ui-profile.json')
    finally:
        subprocess.run(['docker', 'rm', '-f', container], check=False)
    command = ['harbor', 'run', '--path', str(task), '--agent', 'nop' if args.base else 'oracle',
               '--jobs-dir', str(args.output / 'jobs'), '--job-name', 'reviewed-replay',
               '--cpus', args.cpus, '--memory', args.memory, '-n', '1', '--yes']
    if args.delete:
        command += ['--delete']
    if args.override_cpus:
        command += ['--override-cpus', str(args.override_cpus)]
    run(*command)
    trials = list((args.output / 'jobs/reviewed-replay').glob('*/result.json'))
    if len(trials) != 1:
        raise RuntimeError('Expected exactly one Harbor trial')
    trial = json.loads(trials[0].read_text())
    status_path = trials[0].parent / 'verifier/grading-status.json'
    status = json.loads(status_path.read_text()) if status_path.exists() else {}
    reward = (trial.get('verifier_result') or {}).get('rewards', {}).get('reward')
    record = {'image': args.image, 'profile_id': args.profile_id,
              'trial': str(trials[0]), 'status': status, 'reward': reward,
              'profile': json.loads((task / 'tests/ui-profile.json').read_text())}
    (args.output / 'replay.json').write_text(json.dumps(record, indent=2) + '\n')
    if trial.get('exception_info') or status.get('status') != 'scored' or reward not in (0, 1):
        raise RuntimeError('Reviewed replay did not complete a scored trial; see replay.json')

if __name__ == '__main__':
    main()
