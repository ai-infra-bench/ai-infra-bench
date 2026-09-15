#!/usr/bin/env python3
"""Run immutable scoring attacks through the real Harbor entry, plus an Oracle.

Requires Docker and Harbor. All outputs go outside the task; no task files change.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--image', help='Optional already-built image tag/digest')
    parser.add_argument('--harbor', default='harbor')
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).resolve().parents[2]
    labels = ['oracle', 'early_exit', 'forge_reward', 'tamper_boundary', 'delayed_forge']
    records = []
    for label in labels:
        task = args.output / 'tasks' / label
        shutil.copytree(source, task, ignore=shutil.ignore_patterns('validation', '__pycache__'))
        if args.image:
            config = task / 'task.toml'
            config.write_text(config.read_text().replace('[environment]\n',
                              '[environment]\ndocker_image = ' + json.dumps(args.image) + '\n'))
        if label != 'oracle':
            shutil.copy2(Path(__file__).with_name('security-controls') / (label + '.patch'),
                         task / 'solution/implementation.patch')
            (task / 'solution/solve.sh').write_text(
                '#!/bin/bash\nset -euo pipefail\ncd /workspace/pi\ngit apply /solution/implementation.patch\n')
        command = [args.harbor, 'run', '--path', str(task), '--agent', 'oracle', '--env', 'docker',
                   '--jobs-dir', str(args.output / 'jobs'), '--job-name', label,
                   '--n-attempts', '1', '--n-concurrent', '1', '--max-retries', '0', '--yes']
        with (args.output / (label + '.log')).open('w') as log:
            run = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        paths = list((args.output / 'jobs' / label).glob('*/result.json'))
        record = {'label': label, 'command': command, 'cli_exit': run.returncode,
                  'accepted': False, 'input_hashes': {
                      str(p.relative_to(task)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in task.rglob('*') if p.is_file()}}
        if len(paths) == 1:
            trial = json.loads(paths[0].read_text())
            record['trial'] = trial
            result = paths[0].parent / 'verifier/text-behavior/summary.json'
            if result.exists():
                summary = json.loads(result.read_text())
                record['summary'] = summary
                reward = (trial.get('verifier_result') or {}).get('rewards', {}).get('reward')
                expected = 18 if label == 'oracle' else 0
                record['accepted'] = (not trial.get('exception_info') and
                                      summary['case_count'] == 18 and summary['passed'] == expected and
                                      reward == (1 if label == 'oracle' else 0))
                if label == 'tamper_boundary':
                    probe_file = result.parent / 'plain_single/stderr.txt'
                    probes = [json.loads(line) for line in probe_file.read_text().splitlines()
                              if line.startswith('{"probe":')]
                    record['probe'] = probes
                    record['accepted'] &= (len(probes) == 1 and probes[0]['uid'] == 60000 and
                                           all(code in ['EACCES', 'EPERM']
                                               for code in probes[0]['attempts'].values()))
        records.append(record)
        (args.output / 'results.json').write_text(json.dumps(records, indent=2) + '\n')
        print(label, 'PASS' if record['accepted'] else 'FAIL', flush=True)
    return 0 if all(r['accepted'] for r in records) else 1


if __name__ == '__main__':
    raise SystemExit(main())
