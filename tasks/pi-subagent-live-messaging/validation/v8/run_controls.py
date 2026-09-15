#!/usr/bin/env python3
"""Reproduce boundary/negative controls through Harbor without modifying the task."""
import argparse
import concurrent.futures
import json
from pathlib import Path
import shutil
import subprocess


def main():
    here = Path(__file__).resolve().parent
    source = here.parents[1]
    expected = json.loads((here / 'expected-failures.json').read_text())
    labels = [*expected, 'base', 'forge_reward', 'early_exit']
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--image')
    parser.add_argument('--parallel', type=int, default=2, choices=range(1, 5))
    parser.add_argument('--labels', nargs='+', choices=labels, default=labels)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)

    def run(label):
        task = args.output / 'tasks' / label
        shutil.copytree(source, task, ignore=shutil.ignore_patterns('validation', '__pycache__'))
        if args.image:
            p = task / 'task.toml'
            p.write_text(p.read_text().replace('[environment]\n', '[environment]\ndocker_image = ' + json.dumps(args.image) + '\n'))
        if label not in ['base', 'oracle']:
            control = here / 'controls' / label
            shutil.copy2(control / 'submission.patch', task / 'solution/implementation.patch')
            (task / 'solution/solve.sh').write_text('#!/bin/bash\nset -euo pipefail\ncd /workspace/pi\ngit apply /solution/implementation.patch\n')
            for src, dst in [('binding.py', 'interface_binding.py'), ('scenario_binding.py', 'scenario_binding.py')]:
                if (control / src).exists(): shutil.copy2(control / src, task / 'tests' / dst)
        command = ['harbor', 'run', '--path', str(task), '--agent', 'nop' if label == 'base' else 'oracle',
                   '--env', 'docker', '--jobs-dir', str(args.output / 'jobs'), '--job-name', label,
                   '--n-attempts', '1', '--n-concurrent', '1', '--max-retries', '0', '--yes']
        with (args.output / (label + '.log')).open('w') as log:
            proc = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        records = list((args.output / 'jobs' / label).glob('*/result.json'))
        result = {'label': label, 'command': command, 'cli_exit': proc.returncode, 'accepted': False}
        if len(records) == 1:
            trial = json.loads(records[0].read_text())
            result['trial'] = trial
            summary_file = records[0].parent / 'verifier/text-behavior/summary.json'
            if summary_file.exists() and not trial.get('exception_info'):
                summary = json.loads(summary_file.read_text())
                failures = [r['name'] for r in summary['results'] if not r['passed']]
                want = 3 if label == 'base' else (0 if label in ['forge_reward', 'early_exit'] else 24 - len(expected[label]))
                result.update(summary=summary, accepted=(summary['case_count'] == 24 and summary['passed'] == want
                              and trial['verifier_result']['rewards']['reward'] == int(want == 24)
                              and (label not in expected or failures == expected[label])))
        (args.output / (label + '-result.json')).write_text(json.dumps(result, indent=2) + '\n')
        print(label, 'PASS' if result['accepted'] else 'FAIL', flush=True)
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as pool:
        results = list(pool.map(run, args.labels))
    (args.output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    return 0 if all(r['accepted'] for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
