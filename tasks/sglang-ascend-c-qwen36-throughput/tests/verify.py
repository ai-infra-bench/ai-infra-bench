#!/usr/bin/env python3
"""CPU host entrypoint: sandbox grade fresh responses, then validate measurements."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

import performance
import score as scoring


def validate_raw_measurements(root, summary):
    """Recompute full-run summaries from every retained warmup and measured batch."""
    config = performance.DEFAULTS
    if summary.get('contract', {}).get('workload') != config:
        raise ValueError('Raw measurement workload mismatch')

    def same_metrics(actual, expected):
        for key, value in expected.items():
            observed = actual.get(key)
            if (type(observed) not in (int, float) or not math.isfinite(observed)
                    or not math.isclose(observed, value, rel_tol=1e-9, abs_tol=1e-12)):
                raise ValueError('Summary disagrees with raw measurements: ' + key)

    for case in summary['cases']:
        length = case['input_length']
        paths = sorted(root.glob(f'{length}-attempt-*.json'), key=lambda p: int(p.stem.rsplit('-', 1)[1]))
        indices = [int(p.stem.rsplit('-', 1)[1]) for p in paths]
        if not paths or indices != list(range(len(paths))) or len(paths) > config['max_attempts']:
            raise ValueError('Missing or invalid measurement attempt sequence')
        rounds, selected, excluded = [], [], []
        duration = 0.0
        for attempt, path in enumerate(paths):
            record = json.loads(path.read_text())
            rows, elapsed, changes = record['requests'], record['duration_s'], record['compile_changes']
            if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed <= 0:
                raise ValueError('Invalid raw measurement duration')
            if type(changes) is not int or changes < 0:
                raise ValueError('Missing target compilation evidence')
            accepted = attempt >= config['warmup_runs'] and changes == 0
            if record.get('accepted') is not accepted:
                raise ValueError('Warmup or compilation-changing attempt counted as measured')
            if (len(rows) != config['requests'] or any(type(r.get('index')) is not int for r in rows)
                    or sorted(r['index'] for r in rows) != list(range(config['requests']))):
                raise ValueError('Missing or duplicate raw requests')
            for row in rows:
                if row.get('input_tokens') != length or row.get('output_tokens') != config['output_length']:
                    raise ValueError('Raw request token count mismatch')
            metrics = performance.summarize(rows, elapsed)
            if accepted:
                rounds.append(metrics);selected.extend(rows);duration += elapsed
            else:
                excluded.append(attempt)
        if (len(rounds) != config['measured_runs'] or len(case['rounds']) != len(rounds)
                or excluded != case['excluded_attempts']):
            raise ValueError('Selected rounds disagree with raw compilation evidence')
        for actual, expected in zip(case['rounds'], rounds):
            same_metrics(actual, expected)
        same_metrics(case['pooled'], performance.summarize(selected, duration))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--collection', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--code-image', required=True, help='Pinned local CPU Python container image ID')
    p.add_argument('--baseline', type=Path)
    p.add_argument('--deadline', type=float, help='Optional UNIX deadline on this verifier host')
    p.add_argument('--smoke', action='store_true', help='Deployment check only; no optimization credit')
    a = p.parse_args()
    a.collection = a.collection.resolve(); a.output = a.output.resolve()
    a.output.mkdir(parents=True, exist_ok=False)
    result = scoring.initial_result('smoke' if a.smoke else ('candidate' if a.baseline else 'baseline'), a.deadline, a.baseline)
    scoring.write_result(a.output, result)
    here = Path(__file__).resolve().parent
    try:
        if a.deadline is not None and (not math.isfinite(a.deadline) or a.deadline <= 0):
            raise ValueError('Deadline must be a positive finite UNIX timestamp')
        receipt = json.loads((a.collection / 'collection.json').read_text())
        if receipt.get('status') != 'COLLECTED' or receipt.get('mode') != ('smoke' if a.smoke else 'full'):
            raise ValueError('Collection did not complete in the requested mode')
        rc = subprocess.call([sys.executable, str(here / 'evaluate.py'), '--suite', str(here / 'quality100'),
                              '--responses', str(a.collection / 'quality/responses.json'),
                              '--output', str(a.output / 'quality'), '--code-image', a.code_image])
        if rc:
            quality_file = a.output / 'quality/summary.json'
            quality = json.loads(quality_file.read_text()) if quality_file.exists() else None
            result.update(status='INVALID' if quality and quality.get('status') == 'FAILED' else 'ERROR',
                          quality=quality, completed_at=scoring.time.time())
            if a.deadline is not None and scoring.time.time() > a.deadline:
                result.update(status='LATE')
            scoring.write_result(a.output, result)
            return rc
        if a.smoke:
            if a.baseline or a.deadline is not None:
                raise ValueError('Smoke cannot be compared or counted toward a timed score')
            perf = json.loads((a.collection / 'performance/summary.json').read_text())
            if (perf['status'] != 'MEASURED' or not perf['compilation_clean_verified']
                    or [c['input_length'] for c in perf['cases']] != [1024, 4096, 16384, 65536]):
                raise ValueError('Incomplete smoke matrix')
            for case in perf['cases']:
                if (len(case['rounds']) != 1 or case['pooled']['completed_requests'] != 1
                        or case['pooled']['input_tokens'] != case['input_length']
                        or case['pooled']['output_tokens'] != 16):
                    raise ValueError('Invalid smoke token counts')
            result.update(status='SMOKE_PASSED', quality_passed=100, lengths=[1024,4096,16384,65536],
                          completed_at=scoring.time.time(), limitation='Diagnostic only; no optimization score')
            scoring.write_result(a.output, result)
            print(json.dumps(result))
            return 0
        perf = json.loads((a.collection / 'performance/summary.json').read_text())
        validate_raw_measurements(a.collection / 'performance', perf)
        cmd = [sys.executable, str(here / 'score.py'), '--quality', str(a.output / 'quality/summary.json'),
               '--performance', str(a.collection / 'performance/summary.json'), '--output', str(a.output / 'score'),
               '--environment', str(a.collection / 'environment.json'), '--source', str(a.collection / 'source.json')]
        if a.baseline: cmd.extend(['--baseline', str(a.baseline.resolve())])
        if a.deadline is not None: cmd.extend(['--deadline', str(a.deadline)])
        rc = subprocess.call(cmd)
        scoring.write_result(a.output, json.loads((a.output / 'score/summary.json').read_text()))
        return rc
    except Exception as error:
        result.update(status='INVALID' if isinstance(error, (ValueError, KeyError, TypeError)) else 'ERROR',
                      valid=False, score=0.0, improvement_pct=None, error_type=type(error).__name__, error=str(error),
                      completed_at=scoring.time.time())
        if a.deadline is not None and math.isfinite(a.deadline) and a.deadline > 0 and result['completed_at'] > a.deadline:
            result.update(status='LATE')
        scoring.write_result(a.output, result)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
