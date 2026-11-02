#!/usr/bin/env python3
"""Evaluate model quality, fixed-token throughput, or both against SGLang.

No model deployment or device allocation. Standalone model evaluator.
"""
import argparse
import copy
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

# Resolve these verifier modules independently of site-packages.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import grading
import performance

CATEGORIES = ('code', 'math', 'instruction_following')
DECODING = {'temperature': 0, 'top_k': 1, 'max_new_tokens': 1024,
            'ignore_eos': False, 'enable_thinking': False}
ERROR_STATUSES = {'REQUEST_ERROR', 'RESPONSE_ERROR', 'GRADER_ERROR'}


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def related(root, path):
    p = Path(path)
    return p if p.is_absolute() else root / p


def load_suite(root):
    manifest = read(root / 'frozen-manifest.json')
    for key in ('cases.json', 'oracles.json', 'protocol.json'):
        require(key in manifest, 'Missing frozen digest: ' + key)
    for name, expected in manifest.items():
        path = (root / name).resolve()
        require(path.is_relative_to(root.resolve()), 'Manifest escapes suite directory')
        require(sha(path) == expected, 'Frozen input changed: ' + name)
    suite = read(root / 'cases.json')
    cases = suite['cases']
    ids = [c['id'] for c in cases]
    require(len(ids) > 0 and len(ids) == len(set(ids)), 'Empty suite or duplicate IDs')
    require(suite.get('case_count', len(ids)) == len(ids), 'Suite count mismatch')
    oracles = read(root / 'oracles.json')
    require(set(oracles) == set(ids), 'Oracle IDs do not match suite')
    for case in cases:
        require(case['category'] in CATEGORIES and isinstance(case['prompt'], str), 'Invalid case')
        require(case['max_new_tokens'] == 1024, 'Frozen output limit must be 1024')
        oracle = oracles[case['id']]
        if case['category'] == 'instruction_following':
            require(oracle['input_example']['prompt'] == case['prompt'], 'IFEval prompt mismatch')
        elif case['category'] == 'code':
            require(bool(oracle['original_tests']), 'Code oracle has no original tests')
    protocol = read(root / 'protocol.json')
    require(protocol['case_count'] == len(ids), 'Protocol count mismatch')
    return suite, oracles, protocol


def load_verifier(root, protocol, override=None):
    """Verify upstream source bytes before importing the trusted official checker."""
    path = Path(override).resolve() if override else related(root, protocol['official_verifier']).resolve()
    sources = read(related(root, protocol['source_versions']))
    hashes = {}
    for name in ('evaluation_lib.py', 'instructions.py', 'instructions_registry.py', 'instructions_util.py'):
        item = next(x for x in sources['files'] if x['path'] == 'instruction_following_eval/' + name)
        local = path / 'instruction_following_eval' / name
        require(sha(local) == item['sha256'], 'Official verifier changed: ' + name)
        hashes[name] = sha(local)
    init = path / 'instruction_following_eval/__init__.py'
    require(not init.exists() or not init.read_text().strip(), 'Unexpected verifier package initializer')
    sys.path.insert(0, str(path))
    module = importlib.import_module('instruction_following_eval.evaluation_lib')
    require(Path(module.__file__).resolve() == path / 'instruction_following_eval/evaluation_lib.py',
            'Official verifier imported from a different environment')
    # The upstream strict English check uses langdetect. Freeze its randomness
    # and finish lazy profile loading before parallel grading starts.
    from langdetect import DetectorFactory, detect
    DetectorFactory.seed = 0
    require(detect('This is an English sentence used to initialize the language detector.') == 'en',
            'Language detector preflight failed')
    return module, hashes


def validate_rows(rows, cases):
    ids = [r['id'] for r in rows]
    require(len(ids) == len(set(ids)), 'Duplicate response IDs')
    require(set(ids) == {c['id'] for c in cases}, 'Responses must cover every case exactly once')
    categories = {c['id']: c['category'] for c in cases}
    for row in rows:
        require(row['category'] == categories[row['id']], 'Response category mismatch')


def replay(args, suite, oracles):
    report = read(args.responses)
    source = Path(args.source_suite).resolve() if args.source_suite else args.suite
    source_suite, source_oracles, _ = load_suite(source)
    require(report['suite_sha256'] == sha(source / 'cases.json'), 'Response suite digest mismatch')
    validate_rows(report['results'], source_suite['cases'])
    original = {c['id']: c for c in source_suite['cases']}
    for case in suite['cases']:
        require(case == original.get(case['id']), 'Replay prompt or case definition changed')
        require(oracles[case['id']] == source_oracles[case['id']], 'Replay oracle changed')
    require(report['decoding'] == DECODING, 'Replay decoding does not match frozen protocol')
    if args.model:
        require(report['model'] == args.model, 'Replay model mismatch')
    ids = {c['id'] for c in suite['cases']}
    return {
        **report, 'results': [r for r in report['results'] if r['id'] in ids],
        'total': len(ids), 'suite_sha256': sha(args.suite / 'cases.json'),
        'new_model_run': False, 'source_report': str(args.responses.resolve()),
        'source_report_sha256': sha(args.responses),
        'source_suite_sha256': sha(source / 'cases.json'),
        'transport': report.get('transport', 'sglang-native-input-ids'),
    }


def endpoint(value):
    url = urlsplit(value)
    require(url.scheme in ('http', 'https') and url.hostname in ('127.0.0.1', 'localhost', '::1'),
            'Use a loopback endpoint local to the measurement process')
    require(not url.username and not url.password and not url.query and not url.fragment,
            'Endpoint must not contain credentials, query or fragment')
    return value.rstrip('/')


def request_case(base_url, model, case, timeout, api_key=None):
    payload = {
        'model': model, 'messages': [{'role': 'user', 'content': case['prompt']}],
        'temperature': 0, 'top_k': 1, 'max_tokens': case['max_new_tokens'],
        'ignore_eos': False, 'stream': False, 'chat_template_kwargs': {'enable_thinking': False},
    }
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = 'Bearer ' + api_key
    request = Request(base_url + '/chat/completions', data=json.dumps(payload).encode(), headers=headers)
    start = time.monotonic()
    row = {'id': case['id'], 'category': case['category']}
    try:
        with build_opener(ProxyHandler({})).open(request, timeout=timeout) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
        require(len(raw) <= 4 * 1024 * 1024, 'Response exceeds size limit')
        value = json.loads(raw)
        choices = value['choices']
        require(len(choices) == 1, 'Expected one completion')
        choice = choices[0]
        require(isinstance(choice['message']['content'], str), 'Missing text content')
        require(choice['finish_reason'] in ('stop', 'length'), 'Unexpected finish reason')
        # A server that ignores enable_thinking must not silently change the test.
        require(not choice['message'].get('reasoning_content'), 'Unexpected hidden reasoning')
        row.update(request_status='SUCCEEDED', output=choice['message']['content'],
                   metadata={'finish_reason': {'type': choice['finish_reason']},
                             'completion_tokens': value.get('usage', {}).get('completion_tokens'),
                             'prompt_tokens': value.get('usage', {}).get('prompt_tokens')})
    except Exception as error:
        # Avoid logging credentials or server error bodies.
        row.update(request_status='FAILED', error_type=type(error).__name__)
    row['elapsed_s'] = time.monotonic() - start
    return row


def infer(args, suite):
    url = endpoint(args.base_url)
    require(url.endswith('/v1'), '--base-url must include /v1')
    require(bool(args.model), '--model is required for live inference')
    api_key = os.environ.get(args.api_key_env) if args.api_key_env else None
    require(not args.api_key_env or bool(api_key), 'API key environment variable is empty')
    rows = []
    report = {'model': args.model, 'suite_sha256': sha(args.suite / 'cases.json'),
              'decoding': DECODING, 'transport': 'sglang-chat-completions', 'concurrency': args.concurrency,
              'new_model_run': True, 'results': rows, 'started_at': time.time()}
    save(args.output / 'responses.json', report)
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        pending = [pool.submit(request_case, url, args.model, c, args.timeout, api_key) for c in suite['cases']]
        for future in as_completed(pending):
            rows.append(future.result())
            save(args.output / 'responses.json', report)
            save(args.output / 'progress.json', {'phase': 'inference', 'completed': len(rows),
                                                'total': len(suite['cases'])})
    report['total'] = len(rows)
    report['finished_at'] = time.time()
    return report


def compare(baseline, summary):
    for key in ('model', 'contract'):
        require(baseline.get(key) == summary[key], 'Incompatible baseline: ' + key)
    validate_rows(baseline['results'], summary['results'])
    before = {r['id']: r for r in baseline['results']}
    require(all(type(r.get('passed')) is bool for r in before.values()), 'Invalid baseline grades')
    return {
        'regressions': [r['id'] for r in summary['results'] if before[r['id']]['passed'] and not r['passed']],
        'improvements': [r['id'] for r in summary['results'] if not before[r['id']]['passed'] and r['passed']],
    }


def baseline_section(path, mode):
    if not path:
        return None
    value = read(path)
    if value.get('mode') == 'all':
        value = value.get(mode)
    require(isinstance(value, dict) and bool(value), 'Missing baseline section: ' + mode)
    require(value.get('mode', 'quality') == mode, 'Baseline mode mismatch')
    return value


def run_quality(args, emit=True):
    args.suite = args.suite.resolve()
    args.output = args.output.resolve()
    require(args.concurrency > 0 and args.grade_workers > 0 and args.timeout > 0, 'Limits must be positive')
    require(not args.source_suite or args.responses, '--source-suite requires --responses')
    require(not args.output.exists(), 'Output already exists; use a new run directory')
    args.output.mkdir(parents=True)
    start = time.monotonic()
    save(args.output / 'progress.json', {'phase': 'preflight'})
    try:
        suite, oracles, protocol = load_suite(args.suite)
        verifier, verifier_hashes = load_verifier(args.suite, protocol, args.verifier)
        require(bool(re.fullmatch(r'sha256:[0-9a-f]{64}', args.code_image)), 'Use a pinned local Docker image ID')
        # Fail before inference if code grading cannot run in its sandbox.
        probe = grading.code_test('def sandbox_probe(): return 42', {
            'entrypoint': 'sandbox_probe', 'test_imports': [], 'original_tests': ['assert sandbox_probe() == 42'], 'extra_tests': []}, args.code_image)
        require(probe.get('passed') is True, 'Code sandbox preflight failed')
        contract = {
            'cases_sha256': sha(args.suite / 'cases.json'), 'oracles_sha256': sha(args.suite / 'oracles.json'),
            'protocol_sha256': sha(args.suite / 'protocol.json'), 'language_detection_seed': 0,
            'grader_sha256': sha(Path(grading.__file__)), 'runner_sha256': sha(Path(__file__)),
            'code_protocol_sha256': sha(Path(grading.code_protocol.__file__)),
            'code_worker_sha256': sha(Path(grading.__file__).with_name('code_worker.py')),
            'verifier_sha256': verifier_hashes, 'code_image': args.code_image, 'decoding': DECODING,
        }
        report = replay(args, suite, oracles) if args.responses else None
        contract['transport'] = report['transport'] if report else 'sglang-chat-completions'
        baseline = baseline_section(args.baseline, 'quality')
        if baseline:
            require(baseline.get('contract') == contract, 'Incompatible baseline contract')
            require(baseline.get('model') == (report['model'] if report else args.model), 'Incompatible baseline model')
            validate_rows(baseline['results'], suite['cases'])
        report = report or infer(args, suite)
        validate_rows(report['results'], suite['cases'])
        save(args.output / 'responses.json', report)
        cases = {c['id']: c for c in suite['cases']}
        results = []
        with ThreadPoolExecutor(max_workers=args.grade_workers) as pool:
            pending = {pool.submit(grading.evaluate, cases[row['id']], oracles[row['id']], row,
                                   verifier, args.code_image): row for row in report['results']}
            for future in as_completed(pending):
                row = pending[future]
                try:
                    result = future.result()
                except Exception as error:
                    result = {'passed': False, 'status': 'GRADER_ERROR', 'error_type': type(error).__name__}
                results.append({'id': row['id'], 'category': row['category'], **result})
                save(args.output / 'progress.json', {'phase': 'grading', 'completed': len(results),
                                                    'total': len(cases)})
        results.sort(key=lambda r: r['id'])
        total = len(cases)
        passed = sum(r['passed'] for r in results)
        errors = sum(r['status'] in ERROR_STATUSES for r in results)
        summary = {
            'schema_version': 1, 'mode': 'quality', 'model': report['model'], 'suite_version': suite['version'],
            'contract': contract, 'total': total, 'passed': passed, 'all_passed': passed == total,
            'evaluation_errors': errors, 'new_model_run': report['new_model_run'],
            'elapsed_seconds': time.monotonic() - start, 'results': results,
            'status': 'ERROR' if errors else ('PASSED' if passed == total else 'FAILED'),
            'categories': {cat: {'total': sum(r['category'] == cat for r in results),
                                 'passed': sum(r['passed'] for r in results if r['category'] == cat)}
                           for cat in CATEGORIES},
        }
        summary['comparison'] = compare(baseline, summary) if baseline else None
        if args.responses:
            summary['replay_source'] = {'path': str(args.responses.resolve()), 'sha256': sha(args.responses)}
        if args.baseline:
            summary['baseline_source'] = {'path': str(args.baseline.resolve()), 'sha256': sha(args.baseline)}
        save(args.output / 'summary.json', summary)
        raw = {r['id']: r for r in report['results']}
        save(args.output / 'failures.json', [{**r, 'response': raw[r['id']]} for r in results if not r['passed']])
        with (args.output / 'results.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=['id', 'category', 'passed', 'status'], extrasaction='ignore')
            writer.writeheader()
            writer.writerows(results)
        save(args.output / 'progress.json', {'phase': 'complete', 'status': summary['status'],
                                            'completed': total, 'total': total})
        if emit:
            print(json.dumps({'status': summary['status'], 'passed': passed, 'total': total,
                              'new_model_run': summary['new_model_run'], 'summary': str(args.output / 'summary.json')},
                             ensure_ascii=False), flush=True)
        return 2 if errors else (0 if passed == total else 1)
    except BaseException as error:
        save(args.output / 'progress.json', {'phase': 'interrupted' if isinstance(error, KeyboardInterrupt)
                                            else 'error', 'error_type': type(error).__name__})
        raise


def run(args):
    require(args.mode == 'performance' or args.suite, '--suite is required for quality/all mode')
    require(args.mode == 'quality' or not args.responses, 'Response replay supports quality mode only')
    require(args.mode != 'performance' or not args.source_suite, '--source-suite is for quality replay only')
    if args.mode == 'quality':
        require(not args.compile_cache and args.max_throughput_drop_pct == 0,
                'Performance options require performance/all mode')
        return run_quality(args)
    api = SimpleNamespace(require=require, save=save, sha=sha, endpoint=endpoint, baseline_section=baseline_section)
    if args.mode == 'performance':
        return performance.run(args, api)
    require(args.model, '--model is required for all mode')
    performance.validate_options(args, api)
    if args.baseline:
        baseline_section(args.baseline, 'quality')
        baseline_section(args.baseline, 'performance')
    root = args.output.resolve()
    require(not root.exists(), 'Output already exists; use a new run directory')
    root.mkdir(parents=True)
    combined = {'schema_version': 1, 'mode': 'all', 'model': args.model, 'status': 'RUNNING',
                'quality': None, 'performance': None}
    try:
        save(root / 'progress.json', {'phase': 'quality'})
        quality_args = copy.copy(args)
        quality_args.output = root / 'quality'
        code = run_quality(quality_args, emit=False)
        combined['quality'] = read(root / 'quality/summary.json')
        if code:
            combined.update(status=combined['quality']['status'], performance_skipped='quality_not_passed')
        else:
            save(root / 'progress.json', {'phase': 'performance'})
            perf_args = copy.copy(args)
            perf_args.output = root / 'performance'
            code = performance.run(perf_args, api, emit=False)
            combined['performance'] = read(root / 'performance/summary.json')
            combined['status'] = combined['performance']['status']
        save(root / 'summary.json', combined)
        save(root / 'progress.json', {'phase': 'complete', 'status': combined['status']})
        print(json.dumps({'status': combined['status'], 'mode': 'all', 'summary': str(root / 'summary.json')}), flush=True)
        return code
    except BaseException as error:
        # Preserve completed quality results and partial performance evidence.
        for mode in ('quality', 'performance'):
            path = root / mode / 'summary.json'
            if path.exists():
                combined[mode] = read(path)
        combined.update(status='INTERRUPTED' if isinstance(error, KeyboardInterrupt) else 'ERROR',
                        error_type=type(error).__name__)
        save(root / 'summary.json', combined)
        save(root / 'progress.json', {'phase': 'error', 'status': combined['status']})
        raise


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=['quality', 'performance', 'all'], default='quality')
    p.add_argument('--suite', type=Path, help='Frozen suite directory; required for quality/all')
    p.add_argument('--output', type=Path, required=True, help='New run directory; existing results are never overwritten')
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--base-url', help='SGLang loopback chat endpoint, including /v1')
    mode.add_argument('--responses', type=Path, help='Saved inference report for offline replay')
    p.add_argument('--source-suite', type=Path, help='Original frozen suite when replaying a selected subset')
    p.add_argument('--model', help='Served model name; required for live inference')
    p.add_argument('--baseline', type=Path, help='summary.json from this evaluator with the same model and contract')
    p.add_argument('--verifier', type=Path, help='Override official verifier directory; source hashes are still verified')
    p.add_argument('--concurrency', type=int, default=8)
    p.add_argument('--grade-workers', type=int, default=2)
    p.add_argument('--timeout', type=float, default=900, help='Per-request timeout in seconds; no automatic retries')
    p.add_argument('--code-image', default=grading.DEFAULT_IMAGE)
    p.add_argument('--api-key-env', help='Optional environment variable containing the serving API key')
    p.add_argument('--compile-cache', type=Path, action='append', default=[],
                   help='Optional accessible target Triton cache directory; repeat for multiple ranks')
    p.add_argument('--max-throughput-drop-pct', type=float, default=0,
                   help='Allowed per-length throughput drop versus baseline; default 0 percent')
    return p


def main():
    args = parser().parse_args()
    try:
        return run(args)
    except KeyboardInterrupt:
        print('Evaluation interrupted; partial artifacts retained.', file=sys.stderr)
        return 130
    except Exception as error:
        # Do not print external exception bodies (they may contain authenticated URLs).
        message = str(error) if isinstance(error, ValueError) else type(error).__name__
        print('Evaluation error: ' + message, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
