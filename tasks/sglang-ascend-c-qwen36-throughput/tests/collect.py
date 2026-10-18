#!/usr/bin/env python3
"""Collect real model responses and timing; execute generated code only in the host grader."""
import argparse
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
from urllib.request import ProxyHandler, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate
import performance


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--mode', choices=['smoke', 'full'], default='smoke')
    p.add_argument('--model-path', default='/models/Qwen3.6-27B')
    p.add_argument('--launcher', type=Path, default=Path('/workspace/task/launch.py'))
    p.add_argument('--config', type=Path, default=Path('/workspace/task/baseline.json'))
    p.add_argument('--port', type=int, default=30000)
    p.add_argument('--startup-timeout', type=float, default=1200)
    p.add_argument('--request-timeout', type=float, default=7200)
    a = p.parse_args()
    a.output = a.output.resolve()
    a.output.mkdir(parents=True, exist_ok=False)
    suite_root = Path(__file__).resolve().parent / 'quality100'
    suite, _, _ = evaluate.load_suite(suite_root)
    with socket.socket() as s:
        if s.connect_ex(('127.0.0.1', a.port)) == 0:
            raise RuntimeError('Service port is already occupied')
    env = dict(os.environ)
    # A fresh model process imports only the native source tree and image packages.
    env['PYTHONPATH'] = '/workspace/sglang/python' if Path('/workspace/sglang/python').exists() else '/sgl-workspace/sglang/python'
    env['TRITON_CACHE_DIR'] = str(a.output / 'triton-cache')
    env['HF_HUB_OFFLINE'] = env['TRANSFORMERS_OFFLINE'] = '1'
    env['OMP_NUM_THREADS'] = '1'
    env['HCCL_SOCKET_IFNAME'] = env['GLOO_SOCKET_IFNAME'] = 'lo'
    for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy']:
        env.pop(key, None)
    cache = Path(env['TRITON_CACHE_DIR']); cache.mkdir()
    packages = {d.metadata['Name'].lower().replace('_', '-'): d.version for d in metadata.distributions()}
    expected = {'sglang': '0.5.12', 'torch': '2.8.0+cpu', 'torch-npu': '2.8.0.post2',
                'triton-ascend': '3.2.0', 'sgl-kernel-npu': '2026.5.1'}
    for key, value in expected.items():
        if packages.get(key) != value:
            raise ValueError(f'Runtime mismatch: {key}')
    source = Path(env['PYTHONPATH']).parent
    tracked = subprocess.check_output(['git', '-C', str(source), 'ls-files', '-z'])
    untracked = subprocess.check_output(['git', '-C', str(source), 'ls-files', '--others', '--exclude-standard', '-z'])
    source_hashes = {}
    for name in sorted(set((tracked + untracked).decode().split('\0')) - {''}):
        file = source / name
        if file.is_file():
            source_hashes[name] = evaluate.sha(file)
    evaluate.save(a.output / 'source.json', {
        'root': str(source),
        'head': subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip(),
        'files': source_hashes,
        'tree_sha256': hashlib.sha256(json.dumps(source_hashes, sort_keys=True).encode()).hexdigest(),
    })
    # Reapply the vendor's environment after choosing the native source path:
    # graph compilation imports CANN's tbe modules from PYTHONPATH.
    command = ['bash', '-c', 'source /usr/local/Ascend/ascend-toolkit/set_env.sh; exec "$@"',
               'native-service', sys.executable, str(a.launcher.resolve()), '--model-path', a.model_path,
               '--port', str(a.port), '--config', str(a.config.resolve())]
    evaluate.save(a.output / 'environment.json', {
        'packages': packages, 'model': Path(a.model_path).name,
        'model_config_sha256': evaluate.sha(Path(a.model_path) / 'config.json'),
        'weights_index_sha256': evaluate.sha(Path(a.model_path) / 'model.safetensors.index.json'),
        'physical_devices': env.get('ASCEND_RT_VISIBLE_DEVICES'),
        'mode': a.mode, 'command': command, 'started_at': time.time(),
        'config': json.loads(a.config.read_text()), 'launcher_sha256': evaluate.sha(a.launcher),
    })
    process = None
    def cancelled(signum, frame):
        raise KeyboardInterrupt(f'signal {signum}')
    signal.signal(signal.SIGTERM, cancelled)
    opener = build_opener(ProxyHandler({}))
    try:
        with (a.output / 'server.log').open('wb') as log:
            process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=log, start_new_session=True)
        end = time.monotonic() + a.startup_timeout
        while True:
            if process.poll() is not None:
                raise RuntimeError('Native server exited; inspect server.log')
            if time.monotonic() >= end:
                raise TimeoutError('Native server startup timed out')
            try:
                with opener.open(f'http://127.0.0.1:{a.port}/health', timeout=3) as response:
                    if response.status == 200:
                        break
            except Exception:
                time.sleep(2)
        url = f'http://127.0.0.1:{a.port}/v1'
        quality_dir = a.output / 'quality'; quality_dir.mkdir()
        opts = SimpleNamespace(base_url=url, model=Path(a.model_path).name, suite=suite_root,
                               output=quality_dir, concurrency=8, timeout=a.request_timeout, api_key_env=None)
        report = evaluate.infer(opts, suite)
        evaluate.validate_rows(report['results'], suite['cases'])
        evaluate.save(quality_dir / 'responses.json', report)
        if any(row.get('request_status') != 'SUCCEEDED' for row in report['results']):
            raise RuntimeError('Quality request failed; preserve responses for diagnosis')
        opts = SimpleNamespace(base_url=url, model=Path(a.model_path).name,
                               output=a.output / 'performance', responses=None, baseline=None,
                               timeout=a.request_timeout, api_key_env=None, compile_cache=[cache],
                               max_throughput_drop_pct=0)
        # Smoke covers every length but deliberately cannot be scored as full evaluation.
        original = performance.DEFAULTS
        if a.mode == 'smoke':
            performance.DEFAULTS = {**original, 'requests': 1, 'concurrency': 1,
                                    'output_length': 16, 'measured_runs': 1}
        try:
            performance.run(opts, evaluate)
        finally:
            performance.DEFAULTS = original
        evaluate.save(a.output / 'collection.json', {'status': 'COLLECTED', 'mode': a.mode,
                      'quality_cases': len(report['results']), 'finished_at': time.time(),
                      'eligible_for_scoring': a.mode == 'full'})
    except BaseException as error:
        evaluate.save(a.output / 'failure.json', {'type': type(error).__name__, 'message': str(error)})
        raise
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=30)
            except ProcessLookupError:
                pass
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)


if __name__ == '__main__':
    main()
