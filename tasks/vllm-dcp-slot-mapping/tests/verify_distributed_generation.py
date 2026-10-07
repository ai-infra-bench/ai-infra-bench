"""Real TP=2/DCP=2 generation through the normal engine, checked against HF.

No rank/group mocks or manually populated KV cache. The small ordinary model
resource is shared with the agent; workload, reference and assertions are not.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

MODEL = '/opt/models/tiny-qwen3'
PREFIX = 'DISTRIBUTED_GENERATION='


def workloads(profile='batched'):
    if profile in ('chunked', 'interleave1'):
        return {
            'short': ([9 + (i * 7) % 61 for i in range(13)], 2),
            'long': ([73 + (i * 3) % 67 for i in range(62)], 23),
            'later': ([151 + (i * 11) % 83 for i in range(63)], 7),
        }
    assert profile == 'batched'
    return {
        'short': ([4 + i % 41 for i in range(29)], 3),
        'long': ([60 + i % 53 for i in range(61)], 10),
        'later': ([120 + i % 37 for i in range(31)], 6),
    }


def worker(backend, graph, layout, profile='batched'):
    # Environment is set before vLLM imports in this fresh process; candidate
    # modules from earlier component tests cannot substitute the engine here.
    os.environ['VLLM_USE_V2_MODEL_RUNNER'] = '1'
    os.environ['VLLM_WORKER_MULTIPROC_METHOD'] = 'spawn'
    os.environ['VLLM_NO_USAGE_STATS'] = '1'
    os.environ['OMP_NUM_THREADS'] = '1'
    os.environ['VLLM_KV_CACHE_LAYOUT'] = layout
    from vllm import EngineArgs, SamplingParams
    from vllm.v1.engine.llm_engine import LLMEngine
    cfg = EngineArgs(model=MODEL, tokenizer=MODEL, dtype='float16',
        max_model_len=128, tensor_parallel_size=2, decode_context_parallel_size=2,
        cp_kv_cache_interleave_size=1 if profile == 'interleave1' else 2,
        distributed_executor_backend='mp',
        enforce_eager=not graph, async_scheduling=False,
        enable_prefix_caching=False, max_num_seqs=4,
        # The smaller token budget forces ordinary multi-tick prompt processing.
        # The next chunk must combine already cached context and new prompt K/V.
        max_num_batched_tokens=32 if profile == 'chunked' else 128,
        block_size=16 if profile == 'batched' else 32,
        kv_cache_memory_bytes=64 * 1024 * 1024,
        gpu_memory_utilization=0.03, max_logprobs=256,
        # This image's FA3 wrapper has a separate split-scheduler startup
        # incompatibility, reproduced with the original runner as well.
        # Use the supported single-split graph configuration for both runners;
        # this still captures/replays actual attention and DCP collectives.
        attention_config={'backend': backend, 'use_trtllm_attention': False,
            'flash_attn_max_num_splits_for_cuda_graph': 1},
        compilation_config={'mode': 0,
            'cudagraph_mode': 'FULL_DECODE_ONLY' if graph else 'NONE',
            'cudagraph_capture_sizes': [1, 2, 4]},
        disable_log_stats=True, seed=42)
    started = time.monotonic()
    engine = LLMEngine.from_engine_args(cfg)
    setup_seconds = time.monotonic() - started
    cases = workloads(profile)
    def admit(name):
        prompt, budget = cases[name]
        engine.add_request(name, {'prompt_token_ids': prompt},
            SamplingParams(temperature=0, max_tokens=budget, ignore_eos=True,
                           logprobs=256))
    finished, history = {}, []
    admitted_later = False
    try:
        admit('short')
        admit('long')
        for tick in range(100):
            outputs = engine.step()
            history.append({'tick': tick, 'outputs': [
                {'id': o.request_id, 'finished': o.finished,
                 'tokens': list(o.outputs[0].token_ids)} for o in outputs]})
            for output in outputs:
                if output.finished:
                    assert output.request_id not in finished, 'duplicate terminal output'
                    sample = output.outputs[0]
                    finished[output.request_id] = {
                        'tokens': list(sample.token_ids),
                        'logprobs': [{str(k): value.logprob for k, value in lp.items()}
                                    for lp in sample.logprobs]}
            if 'short' in finished and not admitted_later:
                assert 'long' not in finished, 'missing staggered completion'
                admit('later')
                admitted_later = True
            if admitted_later and not engine.has_unfinished_requests():
                break
        assert set(finished) == set(cases), 'missing completion or stuck generation'
        assert not engine.has_unfinished_requests(), 'engine not drained'
        print(PREFIX + json.dumps({'backend': backend, 'graph': graph, 'layout': layout,
            'profile': profile,
            'finished': finished, 'history': history, 'setup_seconds': setup_seconds,
            'total_seconds': time.monotonic() - started}), flush=True)
    finally:
        engine.engine_core.shutdown()


def check(backend, graph, layout, profile='batched'):
    command = [sys.executable, str(Path(__file__).resolve()), '--worker',
               '--backend', backend, '--layout', layout, '--profile', profile]
    if graph:
        command.append('--graph')
    # Explicit layout in each fresh worker: neither a process-local cache nor
    # the ambient environment may silently turn both cases into the same path.
    env = dict(os.environ, OMP_NUM_THREADS='1', VLLM_USE_V2_MODEL_RUNNER='1',
               VLLM_KV_CACHE_LAYOUT=layout, PYTHONUNBUFFERED='1')
    # Parent component checks retain CUDA objects. This worker performs real
    # multi-process initialization in a fresh interpreter, never forked CUDA.
    case = {'backend': backend, 'graph': graph, 'layout': layout, 'profile': profile}
    started = time.monotonic()
    print('DISTRIBUTED_START=' + json.dumps(case), flush=True)
    try:
        completed = subprocess.run(command, env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
    except subprocess.TimeoutExpired as exc:
        # subprocess.run captures output in the exception on timeout, including
        # bytes even with text=True. Preserve it in the supervisor's verifier.log
        # before propagating the original failure; never retry or award success.
        print('DISTRIBUTED_TIMEOUT=' + json.dumps({**case,
            'timeout_seconds': exc.timeout,
            'elapsed_seconds': time.monotonic() - started}), flush=True)
        for stream, output in (('stdout', exc.stdout), ('stderr', exc.stderr)):
            if output is not None:
                if isinstance(output, bytes):
                    output = output.decode('utf-8', errors='replace')
                print(f'DISTRIBUTED_PARTIAL_{stream.upper()}_BEGIN', flush=True)
                print(output, end='' if output.endswith('\n') else '\n', flush=True)
                print(f'DISTRIBUTED_PARTIAL_{stream.upper()}_END', flush=True)
        raise
    print(completed.stdout, flush=True)
    assert completed.returncode == 0, (
        f'{backend} layout={layout} graph={graph}: engine process failed')
    records = [json.loads(line[len(PREFIX):]) for line in completed.stdout.splitlines()
               if line.startswith(PREFIX)]
    assert len(records) == 1, 'missing or duplicate generation observation'
    observation = records[0]
    assert (observation['backend'], observation['graph'], observation['layout']) == (
        backend, graph, layout), 'wrong generation observation configuration'
    assert observation['profile'] == profile, 'wrong workload profile'
    cases = workloads(profile)
    assert set(observation['finished']) == set(cases)

    # Independent model implementation on CPU, using the same immutable weights.
    # Compare distributions, not just repeated-token success or process exit.
    import torch
    from transformers import Qwen3ForCausalLM
    torch.set_num_threads(1)
    model = Qwen3ForCausalLM.from_pretrained(MODEL, torch_dtype=torch.float32,
        attn_implementation='eager', local_files_only=True).eval()
    max_error = 0.0
    for name, (prompt, budget) in cases.items():
        row = observation['finished'][name]
        assert len(row['tokens']) == len(row['logprobs']) == budget
        sequence = list(prompt)
        for token, distribution in zip(row['tokens'], row['logprobs']):
            assert set(distribution) == {str(i) for i in range(256)}
            assert type(token) is int and 0 <= token < 256
            with torch.no_grad():
                logits = model(torch.tensor([sequence])).logits[0, -1].float()
                expected = torch.log_softmax(logits, dim=-1)
            actual = torch.tensor([distribution[str(i)] for i in range(256)])
            assert torch.isfinite(actual).all()
            # FP16 distributed arithmetic versus FP32 CPU: allow numerical
            # rounding and near-tied greedy choices, not wrong KV contents.
            torch.testing.assert_close(actual, expected, rtol=0, atol=0.02)
            assert expected.max() - expected[token] <= 0.02, 'non-greedy output'
            max_error = max(max_error, float((actual - expected).abs().max()))
            sequence.append(token)
    print('DISTRIBUTED_CHECK=' + json.dumps({'backend':backend,'graph':graph,'layout':layout,
        'profile':profile,
        'requests':len(cases),'tokens':sum(b for _,b in cases.values()),
        'max_logprob_error':max_error,'setup_seconds':observation['setup_seconds'],
        'total_seconds':observation['total_seconds']}), flush=True)


def run_group(backend, layout, profile='batched'):
    for graph in (False, True):
        check(backend, graph, layout, profile)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--backend', choices=['FLASH_ATTN', 'FLASHINFER'], required=True)
    parser.add_argument('--layout', choices=['NHD', 'HND'], required=True)
    parser.add_argument('--graph', action='store_true')
    parser.add_argument('--profile', choices=['batched', 'chunked', 'interleave1'],
                        default='batched')
    args = parser.parse_args()
    if args.worker:
        worker(args.backend, args.graph, args.layout, args.profile)
    else:
        check(args.backend, args.graph, args.layout, args.profile)
