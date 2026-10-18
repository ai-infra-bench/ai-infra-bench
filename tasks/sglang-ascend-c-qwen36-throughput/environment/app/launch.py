#!/usr/bin/env python3
"""Launch the native service from an explicit, reviewable configuration."""
import argparse
import json
import os
from pathlib import Path
import sys

FIXED = {
    'tensor_parallel_size': 2, 'dtype': 'bfloat16', 'context_length': 67584,
    'max_running_requests': 64, 'random_seed': 20260904,
}
DEFAULT = {'chunked_prefill_size': 16384, 'page_size': 128,
           'mem_fraction_static': 0.82, 'max_prefill_tokens': 16384}


def command(model, port, config):
    if not set(config) <= set(DEFAULT):
        raise ValueError('Unknown launch configuration field')
    c = {**DEFAULT, **config}
    if type(c['chunked_prefill_size']) is not int or c['chunked_prefill_size'] <= 0:
        raise ValueError('chunked_prefill_size must be positive')
    if type(c['max_prefill_tokens']) is not int or c['max_prefill_tokens'] <= 0:
        raise ValueError('max_prefill_tokens must be positive')
    if c['page_size'] not in (128, 256) or not 0.5 <= c['mem_fraction_static'] <= 0.95:
        raise ValueError('Unsupported page size or memory fraction')
    args = [sys.executable, '-m', 'sglang.launch_server', '--model-path', model,
            '--served-model-name', Path(model).name, '--host', '127.0.0.1', '--port', str(port),
            '--tp-size', '2', '--device', 'npu', '--attention-backend', 'ascend',
            '--dtype', 'bfloat16', '--kv-cache-dtype', 'bfloat16', '--mamba-ssm-dtype', 'bfloat16',
            '--context-length', '67584', '--max-running-requests', '64', '--random-seed', '20260904',
            '--disable-radix-cache', '--disable-custom-all-reduce', '--disable-piecewise-cuda-graph',
            '--cuda-graph-bs', '1', '2', '4', '8', '16', '24', '32', '40', '48', '56', '64',
            '--skip-server-warmup']
    for key, value in c.items():
        args.extend(['--' + key.replace('_', '-'), str(value)])
    return args


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--model-path', default='/models/Qwen3.6-27B')
    p.add_argument('--port', type=int, default=30000)
    p.add_argument('--config', type=Path, default=Path(__file__).with_name('baseline.json'))
    a = p.parse_args()
    os.execv(sys.executable, command(a.model_path, a.port, json.loads(a.config.read_text())))


if __name__ == '__main__':
    main()
