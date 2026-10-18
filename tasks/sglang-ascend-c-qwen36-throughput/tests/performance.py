"""Fixed-token SGLang throughput matrix, following the Qwen reproduction protocol."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import time
from urllib.request import ProxyHandler, Request, build_opener

DEFAULTS = {'input_lengths': [1024, 4096, 16384, 65536], 'output_length': 1024,
            'requests': 16, 'concurrency': 16, 'warmup_runs': 1, 'measured_runs': 3,
            'max_attempts': 12, 'seed': 20260904, 'token_min': 1000, 'token_max': 120000}
METRICS = ('total_throughput_tok_s', 'output_throughput_tok_s', 'request_throughput_req_s',
           'mean_ttft_ms', 'mean_tpot_ms', 'p99_ttft_ms', 'p99_tpot_ms')


def headers(api_key):
    result = {'Content-Type': 'application/json'}
    if api_key:
        result['Authorization'] = 'Bearer ' + api_key
    return result


def server_info(url, timeout, api_key):
    request = Request(url + '/get_server_info', headers=headers(api_key))
    with build_opener(ProxyHandler({})).open(request, timeout=timeout) as response:
        info = json.load(response)
    # Record only model/config fields; never dump an entire server environment.
    return {key: info.get(key) for key in (
        'model_path', 'served_model_name', 'tp_size', 'context_length', 'dtype',
        'disable_radix_cache', 'disable_cuda_graph', 'speculative_algorithm',
        'page_size', 'chunked_prefill_size', 'max_running_requests', 'kv_cache_dtype',
        'mamba_ssm_dtype', 'random_seed')}


def check_server(info, model, config):
    if model not in (info['model_path'], info['served_model_name'], Path(info['model_path'] or '').name):
        raise ValueError('Performance server model mismatch')
    if Path(info['model_path']).name not in ('Qwen3.6-27B', 'Qwen3.6-35B-A3B'):
        raise ValueError('Fixed random-token workload currently supports the two Qwen3.6 models only')
    if (info['tp_size'] != 2 or info['disable_radix_cache'] is not True
            or info['disable_cuda_graph'] is not False or info['speculative_algorithm'] is not None
            or info['dtype'] != 'bfloat16'):
        raise ValueError('Performance requires TP2, BF16, decode graph on, radix cache and speculation off')
    if not isinstance(info['context_length'], int) or info['context_length'] < max(config['input_lengths']) + config['output_length']:
        raise ValueError('Server context is too short for the performance matrix')


def prompts(length, config):
    result = []
    for index in range(config['requests']):
        rng = random.Random(config['seed'] + index)
        result.append([rng.randrange(config['token_min'], config['token_max']) for _ in range(length)])
    return result


def generate(url, ids, output_length, timeout, api_key):
    payload = {'input_ids': ids, 'sampling_params': {
        'temperature': 0, 'top_k': 1, 'max_new_tokens': output_length, 'ignore_eos': True}, 'stream': True}
    started = time.perf_counter()
    first = None
    completion = 0
    prompt_count = None
    done = False
    try:
        request = Request(url + '/generate', data=json.dumps(payload).encode(), headers=headers(api_key))
        with build_opener(ProxyHandler({})).open(request, timeout=timeout) as response:
            while True:
                raw = response.readline(1024 * 1024 + 1)
                if not raw:
                    break
                if time.perf_counter() - started > timeout:
                    raise TimeoutError('Streaming request deadline exceeded')
                if len(raw) > 1024 * 1024:
                    raise ValueError('Oversized streaming event')
                line = raw.decode().strip()
                if not line or line.startswith(':') or line.startswith('event:'):
                    continue
                if not line.startswith('data:'):
                    raise ValueError('Unexpected streaming event')
                data = line[5:].strip()
                if data == '[DONE]':
                    done = True
                    break
                value = json.loads(data)
                if value.get('error'):
                    raise ValueError('Server generation error')
                meta = value.get('meta_info') or {}
                count = meta.get('completion_tokens', 0)
                if type(count) is not int or not completion <= count <= output_length:
                    raise ValueError('Invalid cumulative token count')
                completion = count
                if meta.get('prompt_tokens') is not None:
                    prompt_count = meta['prompt_tokens']
                if count > 0 and first is None:
                    first = time.perf_counter()
        finished = time.perf_counter()
        if not done or first is None or completion != output_length or prompt_count != len(ids):
            raise ValueError('Incomplete stream or exact-token contract violation')
        latency = finished - started
        ttft = first - started
        return {'status': 'SUCCEEDED', 'input_tokens': len(ids), 'output_tokens': completion,
                'latency_s': latency, 'ttft_ms': ttft * 1000,
                'tpot_ms': (latency - ttft) * 1000 / (completion - 1) if completion > 1 else 0.0}
    except Exception as error:
        return {'status': 'FAILED', 'error_type': type(error).__name__,
                'latency_s': time.perf_counter() - started}


def batch(url, inputs, config, timeout, api_key):
    started = time.perf_counter()
    rows = []
    with ThreadPoolExecutor(max_workers=config['concurrency']) as pool:
        pending = {pool.submit(generate, url, ids, config['output_length'], timeout, api_key): index
                   for index, ids in enumerate(inputs)}
        for future in as_completed(pending):
            rows.append({'index': pending[future], **future.result()})
    return sorted(rows, key=lambda row: row['index']), time.perf_counter() - started


def summarize(rows, duration):
    if not rows or duration <= 0 or any(r['status'] != 'SUCCEEDED' for r in rows):
        raise ValueError('Cannot summarize an incomplete or failed performance batch')
    def p99(values):
        return sorted(values)[math.ceil(0.99 * len(values)) - 1]
    ttft = [r['ttft_ms'] for r in rows]
    tpot = [r['tpot_ms'] for r in rows]
    outputs = sum(r['output_tokens'] for r in rows)
    inputs = sum(r['input_tokens'] for r in rows)
    return {'duration_s': duration, 'completed_requests': len(rows), 'input_tokens': inputs,
            'output_tokens': outputs, 'total_throughput_tok_s': (inputs + outputs) / duration,
            'output_throughput_tok_s': outputs / duration, 'request_throughput_req_s': len(rows) / duration,
            'mean_ttft_ms': statistics.mean(ttft), 'mean_tpot_ms': statistics.mean(tpot),
            'p99_ttft_ms': p99(ttft), 'p99_tpot_ms': p99(tpot)}


def cache_snapshot(paths):
    result = {}
    for index, root in enumerate(paths):
        if not root.is_dir():
            raise ValueError('Compile cache directory is missing')
        for path in root.rglob('*.json'):
            if path.name.startswith('__'):
                continue
            try:
                meta = json.loads(path.read_text())
            except (ValueError, OSError):
                # Treat an in-progress metadata write as a cache change too.
                meta = {'name': 'incomplete'}
            if isinstance(meta, dict) and ('kernel_name' in meta or 'name' in meta):
                stat = path.stat()
                result[f'{index}/{path.relative_to(root)}'] = [stat.st_mtime_ns, stat.st_size]
    return result


def validate_baseline(baseline, model, contract):
    if not baseline:
        return
    if (baseline.get('mode') != 'performance' or baseline.get('model') != model
            or baseline.get('contract') != contract or baseline.get('status') not in ('MEASURED', 'PASSED', 'FAILED')):
        raise ValueError('Incompatible performance baseline')
    cases = baseline['cases']
    if [row['input_length'] for row in cases] != contract['workload']['input_lengths']:
        raise ValueError('Performance baseline matrix mismatch')
    for row in cases:
        for key in METRICS:
            value = row['pooled'][key]
            if not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
                raise ValueError('Invalid performance baseline metrics')


def validate_options(args, api):
    api.require(args.base_url and args.model and not args.responses, 'Performance requires a live service and model')
    api.require(0 <= args.max_throughput_drop_pct < 100, 'Throughput drop tolerance must be in [0, 100)')
    api.require(args.baseline or args.max_throughput_drop_pct == 0, 'Drop tolerance requires a baseline')
    api.require(args.timeout > 0, 'Timeout must be positive')
    url = api.endpoint(args.base_url)
    api.require(url.endswith('/v1'), '--base-url must include /v1')
    url = url[:-3]
    key = os.environ.get(args.api_key_env) if args.api_key_env else None
    api.require(not args.api_key_env or key, 'API key environment variable is empty')
    return url, key


def run(args, api, emit=True):
    config = dict(DEFAULTS)
    root = args.output.resolve()
    api.require(not root.exists(), 'Output already exists; use a new run directory')
    url, key = validate_options(args, api)
    caches = [p.resolve() for p in args.compile_cache]
    root.mkdir(parents=True)
    result = {'schema_version': 1, 'mode': 'performance', 'model': args.model, 'status': 'RUNNING',
              'new_model_run': True, 'cases': [], 'comparison': None, 'performance_passed': None}
    try:
        api.save(root / 'progress.json', {'phase': 'preflight'})
        observed = server_info(url, args.timeout, key)
        check_server(observed, args.model, config)
        cache_snapshot(caches)
        contract = {'workload': config, 'tp_size': 2, 'dtype': 'bfloat16', 'radix_cache': False,
                    'decode_graph': True, 'speculation': False, 'transport': 'sglang-generate-stream',
                    'temperature': 0, 'top_k': 1, 'ignore_eos': True, 'compile_monitoring': bool(caches),
                    'runner_sha256': api.sha(Path(__file__)), 'metrics': 'pooled-tokens-over-batch-wall-v1'}
        result.update(contract=contract, server_info=observed, compile_monitoring=bool(caches),
                      compilation_clean_verified=bool(caches),
                      limitation=None if caches else 'Warmup performed; target compilation activity was not observed.')
        baseline = api.baseline_section(args.baseline, 'performance')
        validate_baseline(baseline, args.model, contract)
        for index, length in enumerate(config['input_lengths']):
            inputs = prompts(length, config)
            case = {'input_length': length, 'output_length': config['output_length'],
                    'prompts_sha256': hashlib.sha256(json.dumps(inputs, separators=(',', ':')).encode()).hexdigest(),
                    'rounds': [], 'excluded_attempts': []}
            if baseline:
                api.require(case['prompts_sha256'] == baseline['cases'][index]['prompts_sha256'],
                            'Performance workload digest mismatch')
            selected_rows = []
            duration = 0.0
            for attempt in range(config['max_attempts']):
                api.save(root / 'progress.json', {'phase': 'warmup' if attempt < config['warmup_runs'] else 'measuring',
                                                'input_length': length, 'attempt': attempt,
                                                'accepted_rounds': len(case['rounds'])})
                before = cache_snapshot(caches)
                rows, elapsed = batch(url, inputs, config, args.timeout, key)
                after = cache_snapshot(caches)
                changes = sum(before.get(k) != after.get(k) for k in before.keys() | after.keys())
                accepted = attempt >= config['warmup_runs'] and changes == 0
                record = {'requests': rows, 'duration_s': elapsed, 'accepted': accepted,
                          'compile_changes': changes if caches else None}
                api.save(root / f'{length}-attempt-{attempt}.json', record)
                metrics = summarize(rows, elapsed)  # Failed requests invalidate the round; never drop them.
                api.require(not caches or after, 'No target kernel metadata observed in the supplied compile cache')
                if accepted:
                    case['rounds'].append(metrics)
                    selected_rows.extend(rows)
                    duration += elapsed
                else:
                    case['excluded_attempts'].append(attempt)
                if len(case['rounds']) == config['measured_runs']:
                    break
            api.require(len(case['rounds']) == config['measured_runs'], 'Not enough compilation-clean measurement rounds')
            case['pooled'] = summarize(selected_rows, duration)
            result['cases'].append(case)
            api.save(root / 'partial.json', result)
        api.require(server_info(url, args.timeout, key) == observed, 'Server configuration changed during evaluation')
        if baseline:
            comparisons = []
            for current, previous in zip(result['cases'], baseline['cases']):
                api.require(current['prompts_sha256'] == previous['prompts_sha256'], 'Performance workload digest mismatch')
                ratios = {metric: current['pooled'][metric] / previous['pooled'][metric] for metric in METRICS}
                comparisons.append({'input_length': current['input_length'], 'ratios': ratios,
                    'throughput_passed': ratios['total_throughput_tok_s'] >= 1 - args.max_throughput_drop_pct / 100})
            result['comparison'] = comparisons
            result['baseline_sha256'] = api.sha(args.baseline)
            result['max_throughput_drop_pct'] = args.max_throughput_drop_pct
            result['performance_passed'] = all(x['throughput_passed'] for x in comparisons)
        result['status'] = 'MEASURED' if not baseline else ('PASSED' if result['performance_passed'] else 'FAILED')
        api.save(root / 'summary.json', result)
        with (root / 'results.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=['input_length', 'output_length', *METRICS], extrasaction='ignore')
            writer.writeheader()
            writer.writerows({'input_length': c['input_length'], 'output_length': c['output_length'], **c['pooled']}
                             for c in result['cases'])
        api.save(root / 'progress.json', {'phase': 'complete', 'status': result['status']})
        if emit:
            print(json.dumps({'status': result['status'], 'mode': 'performance', 'summary': str(root / 'summary.json')}), flush=True)
        return 1 if result['status'] == 'FAILED' else 0
    except BaseException as error:
        result.update(status='INTERRUPTED' if isinstance(error, KeyboardInterrupt) else 'ERROR',
                      error_type=type(error).__name__, compilation_clean_verified=False)
        api.save(root / 'summary.json', result)
        api.save(root / 'progress.json', {'phase': 'error', 'status': result['status']})
        raise
