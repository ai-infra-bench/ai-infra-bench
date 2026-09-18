#!/usr/bin/env python3
"""Small real-model mp regressions against an independent Transformers result.

Weights, prompts and expected output are created outside candidate imports.
Candidate execution uses the normal LLM entry point and real executor/workers,
attention, KV cache, sampler, scheduler and output collection.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import nullcontext

PROMPTS = [[7, 11, 19], list(range(20, 57)), list(range(61, 74))]
LIMITS = [4, 7, 5]
FRESH_PROMPT = [83, 17, 29]


class PendingOutputProbe:
    """Hold worker progress until two submissions share a request.

    This uses the existing mp executor RPC interface only as a test gate. Real
    scheduling, request submissions and subsequent model execution are unchanged.
    The deadline bounds a failed liveness check; it is not a speed requirement.
    """
    def __init__(self, executor):
        import socket
        import threading
        self.executor = executor
        self.server = socket.socket()
        self.server.bind(('127.0.0.1', 0))
        self.server.listen(2)
        self.server.settimeout(60)
        self.ready = threading.Event()
        self.release = threading.Event()
        self.witnessed = False
        self.errors = []
        self.seen = set()
        self.original = executor.execute_model
        self.thread = threading.Thread(target=self.control, daemon=True)

    def control(self):
        peers = []
        try:
            for _ in range(2):
                peer, _ = self.server.accept()
                peers.append(peer)
            self.ready.set()
            if not self.release.wait(60):
                self.errors.append('no overlapping request submission before output release')
        except Exception as exc:
            self.errors.append(repr(exc))
        finally:
            for peer in peers:
                try:
                    peer.sendall(b'1')
                finally:
                    peer.close()
            self.server.close()

    def __enter__(self):
        self.thread.start()
        port = self.server.getsockname()[1]

        def hold_worker(worker, port):
            import socket
            with socket.create_connection(('127.0.0.1', port), timeout=120) as peer:
                assert peer.recv(1) == b'1'

        self.gate_future = self.executor.collective_rpc(
            hold_worker, args=(port,), non_block=True)
        assert self.ready.wait(60), 'workers did not reach the output gate'

        def submit(step, *args, **kwargs):
            result = self.original(step, *args, **kwargs)
            ids = set(step.num_scheduled_tokens)
            if ids & self.seen and not self.release.is_set() and not self.errors:
                self.witnessed = True
                self.release.set()
            self.seen.update(ids)
            return result

        self.executor.execute_model = submit
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release.set()
        self.thread.join(timeout=65)
        self.executor.execute_model = self.original
        if exc_type is None:
            self.gate_future.result()
            assert self.witnessed and not self.errors, (
                'mp executor failed to submit another step while output was pending', self.errors)
            print('MP_PENDING_OUTPUT_OVERLAP=PASS', flush=True)


def private_json(path, value):
    # Create with restrictive permissions before writing any answer bytes.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, indent=2)


def reference(model_dir):
    import torch
    from transformers import OPTConfig, OPTForCausalLM
    torch.set_num_threads(1)
    torch.manual_seed(937)
    config = OPTConfig(vocab_size=128, hidden_size=64, ffn_dim=128,
        num_hidden_layers=4, num_attention_heads=4, word_embed_proj_dim=64,
        max_position_embeddings=128, dropout=0.0, attention_dropout=0.0,
        init_std=0.1, tie_word_embeddings=False, bos_token_id=1,
        eos_token_id=2, pad_token_id=0)
    config._attn_implementation = 'eager'
    model = OPTForCausalLM(config).eval()
    model.save_pretrained(model_dir)
    def decode(prompt, limit):
        ids = list(prompt)
        with torch.inference_mode():
            for _ in range(limit):
                logits = model(torch.tensor([ids]), use_cache=False).logits[0, -1]
                ids.append(int(logits.argmax()))
        return ids[len(prompt):]
    return {'initial': [decode(p, n) for p, n in zip(PROMPTS, LIMITS)],
            'fresh': [decode(FRESH_PROMPT, 3)]}


def candidate(model_dir, case, output_path):
    import vllm
    assert str(Path(vllm.__file__).resolve()).startswith('/workspace/repo/')
    from vllm import LLM, SamplingParams
    async_mode, pp = {'async_pp2': (True, 2), 'sync_pp2': (False, 2),
                      'async_pp1': (True, 1), 'sync_pp1': (False, 1)}[case]
    llm = LLM(model=model_dir, skip_tokenizer_init=True, dtype='float16',
        pipeline_parallel_size=pp, tensor_parallel_size=1,
        distributed_executor_backend='mp', async_scheduling=async_mode,
        enable_chunked_prefill=True, enable_prefix_caching=False,
        max_model_len=64, max_num_batched_tokens=8, max_num_seqs=4,
        kv_cache_memory_bytes=16 * 1024 * 1024, gpu_memory_utilization=0.1,
        enforce_eager=True, seed=937, disable_log_stats=True)
    def generate(prompts, limits):
        results = llm.generate([{'prompt_token_ids': p} for p in prompts],
            [SamplingParams(temperature=0, max_tokens=n, ignore_eos=True,
                            detokenize=False) for n in limits], use_tqdm=False)
        assert all(r.finished for r in results)
        return [list(r.outputs[0].token_ids) for r in results]
    # The frontend is local in this case; the mp executor still owns two real
    # worker processes. Gate worker responses without replacing token transport.
    probe = PendingOutputProbe(llm.llm_engine.model_executor) if case == 'async_pp2' else nullcontext()
    with probe:
        initial = generate(PROMPTS, LIMITS)
    observed = {'initial': initial, 'fresh': generate([FRESH_PROMPT], [3])}
    Path(output_path).write_text(json.dumps(observed))


def supervise(log_dir, cases=('async_pp2', 'sync_pp2', 'async_pp1', 'sync_pp1')):
    root = Path(log_dir)
    root.mkdir(parents=True, exist_ok=True)
    model_dir = Path('/trusted/mp-e2e-model')
    model_dir.mkdir(parents=True, exist_ok=True)
    expected = reference(model_dir)
    private_json(root / 'mp-e2e-expected.json', expected)
    # Input artifacts are readable by workers but remain root-owned.
    for p in model_dir.iterdir():
        p.chmod(0o444)
    results = {}
    for case in cases:
        began = time.monotonic()
        scratch = Path(tempfile.mkdtemp(prefix='async-pp-e2e-'))
        os.chown(scratch, 65534, 65534)
        output_path = scratch / 'output.json'
        env = {k: v for k, v in os.environ.items()
               if k not in ('PYTHONHOME', 'PYTHONPATH', 'RANK', 'LOCAL_RANK', 'WORLD_SIZE')
               and not k.startswith('ASYNC_PP_')}
        env.update(PYTHONPATH='/workspace/repo', HOME=str(scratch), TMPDIR=str(scratch),
                   HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                   OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
                   VLLM_WORKER_MULTIPROC_METHOD='spawn',
                   TRITON_CACHE_DIR=str(scratch / 'triton'),
                   TORCHINDUCTOR_CACHE_DIR=str(scratch / 'inductor'))
        if case == 'async_pp2':
            env['VLLM_ENABLE_V1_MULTIPROCESSING'] = '0'
        argv = ['setpriv', '--reuid=65534', '--regid=65534', '--init-groups',
                '--no-new-privs', '--', sys.executable, '-s', str(Path(__file__).resolve()),
                '--case', case, '--model', str(model_dir), '--output', str(output_path)]
        proc = None
        try:
            with (root / f'mp-e2e-{case}.log').open('w') as log:
                proc = subprocess.Popen(argv, env=env, cwd='/trusted/staging',
                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                proc.wait(timeout=240)
            actual = json.loads(output_path.read_text()) if output_path.exists() else None
            results[case] = {'passed': proc.returncode == 0 and actual == expected,
                             'exit_code': proc.returncode, 'actual': actual}
        except Exception as exc:
            results[case] = {'passed': False, 'error': repr(exc)}
        finally:
            if proc is not None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
            results[case]['elapsed_seconds'] = round(time.monotonic() - began, 3)
            private_json(root / 'mp-e2e.json', results)
            # Later candidates share the worker uid; remove prior answer files.
            shutil.rmtree(scratch)
    return 0 if all(r['passed'] for r in results.values()) else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model')
    parser.add_argument('--case')
    parser.add_argument('--output')
    parser.add_argument('--log-dir', default='/logs/verifier')
    parser.add_argument('--cases', nargs='+', choices=('async_pp2', 'sync_pp2', 'async_pp1', 'sync_pp1'),
                        default=('async_pp2', 'sync_pp2', 'async_pp1', 'sync_pp1'))
    args = parser.parse_args()
    if args.case:
        candidate(args.model, args.case, args.output)
    else:
        raise SystemExit(supervise(args.log_dir, args.cases))
