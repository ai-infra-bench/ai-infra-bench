#!/usr/bin/env python3
"""Trusted parent, fresh expectations and authenticated completion.

The worker executes precompiled task code as nobody. Candidate source is loaded
only there. Scoring includes actual scheduler/runner model inputs and retained
storage; completion authentication is scoped to the documented Python controls.
"""
import json
from pathlib import Path
import sys
import time
import traceback
import types

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))
from completion_channel import execute_suite
from encoder_contract import expected, workload

WORKER_FILES = ('encoder_runtime.py', 'encoder_storage.py',
                'encoder_capacity_worker.py', 'encoder_scenarios.py')
WORKER_CODE = '\n\n'.join((TESTS / name).read_text() for name in WORKER_FILES)
_COMPILED_WORKER = compile(WORKER_CODE, '<encoder-behavior-suite>', 'exec')
REQUIRED_STAGES = {'allocator', 'capacity', 'resource_progress', 'whole_reservation',
                   'text_and_empty', 'storage', 'main_inputs', 'eagle_inputs'}


def run_suite(inputs, checkpoint):
    # Load exact precompiled verifier code, never a candidate-shadowable sibling
    # module. The native channel authenticates this outer function's code object.
    module = types.ModuleType('_encoder_behavior_suite')
    module.__file__ = str(TESTS / 'encoder_runtime.py')
    sys.modules[module.__name__] = module
    exec(_COMPILED_WORKER, module.__dict__)
    checkpoint(module.run_checks(inputs))


RUN_SUITE = run_suite


def expected_observations():
    # Also used by the curator's full-report-forgery control. These plausible
    # values alone do not prove that the original suite completed.
    return {
        'allocator': [0, 0, 5, 5, 0, 3, 8, 2],
        'capacity': {
            'dummy': [{'scheduler': [max(1, n), max(1, n)], 'runner': max(1, n)}
                      for n in (8, 4, 9, 0, 0, 0)],
            'video': [{'scheduler': [n, n], 'runner': n} for n in (16, 48)]},
        'resource_progress': {'zero_resource_progress': True,
                              'reuse_and_eviction': True, 'fresh_admission': True},
        'whole_reservation': {'full_item_reserved': True},
        'text_and_empty': {'text_and_empty_advance': True},
        'storage': [{'span': span, 'payload_bytes': 512, 'runtime_bytes': 512, 'profile_bytes': 512}
                    for span in (16, 128, 4096)],
        'main_inputs': {'model_inputs_checked': True},
        'eagle_inputs': {'model_inputs_checked': True},
    }


def stage_matches(name, observed, wanted):
    if name == 'capacity':
        if not isinstance(observed, dict) or set(observed) != {'dummy', 'video'}:
            return False
        if observed['video'] != wanted['video'] or not isinstance(observed['dummy'], list):
            return False
        cases = observed['dummy']
        zeros = [dict(scheduler=[compute, cache], runner=min(compute, cache))
                 for compute in (0, 1) for cache in (0, 1)]
        return (len(cases) == 6 and cases[:3] == wanted['dummy'][:3]
                and all(case in zeros for case in cases[3:]))
    if name == 'storage':
        if not isinstance(observed, list) or len(observed) != 3:
            return False
        for item, span in zip(observed, (16, 128, 4096)):
            if not isinstance(item, dict) or set(item) != {'span', 'payload_bytes', 'runtime_bytes', 'profile_bytes'}:
                return False
            if item['span'] != span:
                return False
            if any(type(item[k]) is not int or item[k] < 0 for k in ('payload_bytes', 'runtime_bytes', 'profile_bytes')):
                return False
            if item['payload_bytes'] > item['runtime_bytes']:
                return False
            if item['profile_bytes'] < item['runtime_bytes']:
                return False
        first = observed[0]['payload_bytes']
        return all(item['payload_bytes'] <= first + max(256, first // 2)
                   for item in observed[1:])
    return observed == wanted


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def run_worker():
    inputs = workload()
    wanted = expected(inputs)
    try:
        completion = execute_suite(RUN_SUITE, inputs, timeout=540)
    except Exception as exc:
        return {'verdict': 'FAIL', 'reason': 'worker_setup_failed',
                'error': str(exc), 'traceback': traceback.format_exc()}
    if 'error' in completion:
        return {'verdict': 'FAIL', 'reason': completion['error'],
                'worker_status': completion['worker_status'],
                'diagnostic': completion['diagnostic']}
    try:
        payload = json.loads(completion['payload'], object_pairs_hook=reject_duplicate_keys)
    except (ValueError, TypeError) as exc:
        return {'verdict': 'FAIL', 'reason': 'worker_output_invalid_json', 'error': str(exc)}
    if not isinstance(payload, dict):
        return {'verdict': 'FAIL', 'reason': 'worker_output_not_object'}
    stages, failures = payload.get('stages'), payload.get('failures')
    if not isinstance(stages, dict) or not isinstance(failures, dict):
        return {'verdict': 'FAIL', 'reason': 'worker_report_malformed'}
    if failures:
        return {'verdict': 'FAIL', 'reason': 'worker_reported_failures_with_zero_exit',
                'failures': failures, 'completed_stages': sorted(stages),
                'timings': payload.get('timings')}
    if set(stages) != REQUIRED_STAGES:
        return {'verdict': 'FAIL', 'reason': 'incomplete_stage_coverage',
                'missing': sorted(REQUIRED_STAGES - set(stages)),
                'unexpected': sorted(set(stages) - REQUIRED_STAGES)}
    mismatched = [name for name, value in expected_observations().items()
                  if not stage_matches(name, stages[name], value)]
    if mismatched:
        return {'verdict': 'FAIL', 'reason': 'behavioral_observation_mismatch',
                'mismatched_stages': mismatched, 'stages': stages}
    if payload.get('observations') != wanted:
        return {'verdict': 'FAIL', 'reason': 'fresh_behavioral_observation_mismatch',
                'inputs': inputs, 'observed': payload.get('observations'), 'expected': wanted}
    return {'verdict': 'PASS', 'worker_exit': 0, 'stages': stages,
            'timings': payload.get('timings'), 'inputs': inputs,
            'observations': payload['observations']}


def main():
    import os
    if os.getuid() != 0:
        raise RuntimeError('verifier requires a root scoring parent')
    started = time.monotonic()
    result = run_worker()
    result['elapsed_seconds'] = round(time.monotonic() - started, 4)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result['verdict'] == 'PASS':
        print('ENCODER_CACHE_VERIFIER=PASS')
        return 0
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
