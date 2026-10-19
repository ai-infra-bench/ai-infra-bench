#!/usr/bin/env python3
"""Trusted host-side validation of complete quality and performance reports."""
import argparse
import hashlib
import re
import json
import math
from pathlib import Path
import statistics
import time

import performance


def validate(quality, perf):
    if quality.get('status') != 'PASSED' or quality.get('passed') != 100 or quality.get('total') != 100:
        raise ValueError('All 100 quality cases must pass')
    results = quality.get('results', [])
    if len(results) != 100 or len({r['id'] for r in results}) != 100 or not all(r.get('passed') is True for r in results):
        raise ValueError('Missing or failed quality case')
    if perf.get('status') != 'MEASURED' or perf.get('compilation_clean_verified') is not True:
        raise ValueError('Complete compilation-clean performance measurements required')
    if perf.get('contract', {}).get('workload') != performance.DEFAULTS:
        raise ValueError('Smoke or altered performance workload cannot receive a score')
    if quality.get('model') != 'Qwen3.6-27B' or quality.get('model') != perf.get('model'):
        raise ValueError('This task requires Qwen3.6-27B for both quality and performance')
    observed = perf.get('server_info', {})
    if any(observed.get(key) != 'bfloat16' for key in ('dtype', 'kv_cache_dtype', 'mamba_ssm_dtype')):
        raise ValueError('Model, KV cache and recurrent state must remain BF16')
    if (observed.get('tp_size') != 2 or observed.get('context_length') != 67584
            or observed.get('disable_radix_cache') is not True
            or observed.get('disable_cuda_graph') is not False
            or observed.get('speculative_algorithm') is not None):
        raise ValueError('Serving configuration violates the fixed task contract')
    cases = perf.get('cases', [])
    if [c['input_length'] for c in cases] != performance.DEFAULTS['input_lengths']:
        raise ValueError('Incomplete length matrix')
    for case in cases:
        rounds = case.get('rounds', [])
        if len(rounds) != 3 or case.get('output_length') != 1024:
            raise ValueError('Incomplete measurement rounds')
        request_count = performance.DEFAULTS['requests']
        for row, count in [(r, request_count) for r in rounds] + [(case['pooled'], request_count * len(rounds))]:
            duration = row.get('duration_s')
            if type(duration) not in (float, int) or not math.isfinite(duration) or duration <= 0:
                raise ValueError('Invalid measurement duration')
            if (row.get('completed_requests') != count or row.get('input_tokens') != count * case['input_length']
                    or row.get('output_tokens') != count * 1024):
                raise ValueError('Request or token count mismatch')
            for key in performance.METRICS:
                value = row.get(key)
                if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
                    raise ValueError('Invalid performance metric')
            expected = (row['input_tokens'] + row['output_tokens']) / row['duration_s']
            if not math.isclose(row['total_throughput_tok_s'], expected, rel_tol=1e-9):
                raise ValueError('Inconsistent throughput accounting')
            if (not math.isclose(row['output_throughput_tok_s'], row['output_tokens'] / duration, rel_tol=1e-9)
                    or not math.isclose(row['request_throughput_req_s'], count / duration, rel_tol=1e-9)):
                raise ValueError('Inconsistent output or request throughput accounting')
        if not math.isclose(case['pooled']['duration_s'], sum(r['duration_s'] for r in rounds), rel_tol=1e-9):
            raise ValueError('Pooled duration does not match measured rounds')


def compare(quality, perf, base_quality, base_perf):
    validate(quality, perf)
    validate(base_quality, base_perf)
    if quality['contract'] != base_quality['contract'] or perf['contract'] != base_perf['contract']:
        raise ValueError('Incompatible measurement or grading contracts')
    if quality['model'] != base_quality['model']:
        raise ValueError('Cross-model comparisons are not allowed')
    if {r['id'] for r in quality['results']} != {r['id'] for r in base_quality['results']}:
        raise ValueError('Different quality cases')
    ratios, variability = {}, {}
    for current, previous in zip(perf['cases'], base_perf['cases']):
        if current['prompts_sha256'] != previous['prompts_sha256']:
            raise ValueError('Different performance inputs')
        length = str(current['input_length'])
        ratios[length] = current['pooled']['total_throughput_tok_s'] / previous['pooled']['total_throughput_tok_s']
        variability[length] = {}
        for label, row in [('baseline', previous), ('candidate', current)]:
            samples = [r['total_throughput_tok_s'] for r in row['rounds']]
            variability[length][label + '_cv'] = statistics.stdev(samples) / statistics.mean(samples)
    return {'score': math.exp(sum(math.log(r) for r in ratios.values()) / 4),
            'throughput_ratios': ratios, 'round_variability': variability,
            'regressed_lengths': [int(k) for k, v in ratios.items() if v < 1]}


TASK_ID = 'infra-bench-opt/sglang-ascend-c-qwen36-throughput'
SCHEMA = 'infra-bench-opt.result.v1'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def initial_result(kind='candidate', deadline=None, baseline=None):
    return {'schema_version': SCHEMA, 'benchmark': 'infra-bench-opt', 'task_id': TASK_ID,
            'kind': kind, 'status': 'ERROR', 'valid': False, 'score': None,
            'improvement_pct': None, 'improved': None, 'timed': deadline is not None,
            'deadline': deadline if deadline is not None and math.isfinite(deadline) else None,
            'baseline_sha256': digest(baseline) if baseline and Path(baseline).is_file() else None,
            'source_sha256': None, 'completed_at': time.time()}


def write_result(root, result):
    temporary = root / 'summary.json.tmp'
    temporary.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    temporary.replace(root / 'summary.json')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--quality', type=Path, required=True)
    p.add_argument('--performance', type=Path, required=True)
    p.add_argument('--environment', type=Path, required=True)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--baseline', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--deadline', type=float, help='Must match the trusted trial receipt')
    p.add_argument('--trial', type=Path, help='Trusted controller trial receipt created before measurement')
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    result = initial_result('candidate' if a.baseline else 'baseline', a.deadline, a.baseline)
    write_result(a.output, result)
    try:
        if a.deadline is not None and (not math.isfinite(a.deadline) or a.deadline <= 0):
            raise ValueError('Deadline must be a positive finite UNIX timestamp')
        if a.deadline is not None and not a.trial:
            raise ValueError('Timed candidates require a registered trial receipt')
        quality, perf = json.loads(a.quality.read_text()), json.loads(a.performance.read_text())
        environment = json.loads(a.environment.read_text())
        source = json.loads(a.source.read_text())
        validate(quality, perf)
        fingerprint = {'source': source, 'config': environment.get('config'),
                       'launcher_sha256': environment.get('launcher_sha256')}
        result.update(status='BASELINE_VALIDATED', valid=True, score=1.0, improvement_pct=0.0, improved=False,
                      quality=quality, performance=perf, environment=environment, source=source,
                      source_sha256=hashlib.sha256(json.dumps(fingerprint, sort_keys=True, allow_nan=False).encode()).hexdigest())
        if a.trial:
            if not a.baseline:raise ValueError('A timed trial requires a frozen baseline')
            trial = json.loads(a.trial.read_text())
            if (trial.get('schema_version') != 'infra-bench-opt.trial.v1' or trial.get('task_id') != TASK_ID
                    or trial.get('baseline_sha256') != result['baseline_sha256']
                    or trial.get('source_sha256') != result['source_sha256']):
                raise ValueError('Trial receipt does not match this candidate and baseline')
            if (type(trial.get('deadline')) not in (int,float) or not math.isfinite(trial['deadline'])
                    or type(trial.get('started_at')) not in (int,float) or not math.isfinite(trial['started_at'])
                    or not 0 < trial['started_at'] < trial['deadline'] or trial['started_at'] > time.time()):
                raise ValueError('Invalid trial timing')
            if a.deadline is not None and a.deadline != trial['deadline']:
                raise ValueError('Different trial deadline')
            if (not re.fullmatch(r'[0-9a-f]{32}', str(trial.get('trial_id','')))
                    or not re.fullmatch(r'[0-9a-f]{32}', str(trial.get('campaign_id','')))
                    or trial.get('budget_seconds') != 28800
                    or type(trial.get('campaign_started_at')) not in (float,int)
                    or not math.isfinite(trial['campaign_started_at'])
                    or not 0 < trial['campaign_started_at'] <= trial['started_at']
                    or not math.isclose(trial['deadline']-trial['campaign_started_at'],28800,abs_tol=1e-6)):
                raise ValueError('This task requires a registered eight-hour campaign')
            collected_at = environment.get('started_at')
            if (type(collected_at) not in (int, float) or not math.isfinite(collected_at)
                    or not trial['started_at'] <= collected_at <= time.time()):
                raise ValueError('Measurement must start after registration; historical replay is untimed only')
            a.deadline = trial['deadline']
            result.update(timed=True,deadline=a.deadline,trial_id=trial['trial_id'],campaign_id=trial['campaign_id'])
        if a.baseline:
            baseline = json.loads(a.baseline.read_text())
            if (baseline.get('schema_version') != SCHEMA or baseline.get('benchmark') != 'infra-bench-opt'
                    or baseline.get('status') != 'BASELINE_VALIDATED' or baseline.get('kind') != 'baseline'
                    or type(baseline.get('score')) not in (int,float)
                    or baseline.get('valid') is not True or baseline.get('score') != 1
                    or baseline.get('task_id') != TASK_ID):
                raise ValueError('A validated optimization-track baseline is required; regrade legacy records')
            for key in ['packages', 'model', 'model_config_sha256', 'weights_index_sha256', 'physical_devices']:
                if environment[key] != baseline['environment'][key]:
                    raise ValueError('Different baseline environment: ' + key)
            result.update(compare(quality, perf, baseline['quality'], baseline['performance']))
            result.update(status='VALID', improvement_pct=(result['score'] - 1) * 100,
                          improved=result['score'] > 1)
    except (ValueError, KeyError, TypeError, ZeroDivisionError) as error:
        result.update(status='INVALID', valid=False, score=None, improvement_pct=None, improved=None, error=str(error))
    except OSError as error:
        result.update(status='ERROR', valid=False, score=None, improvement_pct=None, improved=None, error=type(error).__name__)
    result['completed_at'] = time.time()
    if a.deadline is not None and math.isfinite(a.deadline) and a.deadline > 0 and result['completed_at'] > a.deadline:
        result.update(status='LATE', valid=False, score=None, improvement_pct=None, improved=None)
    write_result(a.output, result)
    print(json.dumps({k: v for k, v in result.items() if k not in ['quality', 'performance', 'environment', 'source']}, allow_nan=False))
    return 0 if result['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
