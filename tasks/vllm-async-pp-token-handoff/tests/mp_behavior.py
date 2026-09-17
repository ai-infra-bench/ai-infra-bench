"""Behavioral scenarios through a real scheduler and mp executor/Worker lifecycle."""
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time

from worker_fixtures import install_probe, configure_probe, read_probe


class PrefillGate:
    def __init__(self, expected):
        self.expected = expected
        self.server = socket.socket()
        self.server.bind(('127.0.0.1', 0))
        self.server.listen(2)
        self.server.settimeout(0.2)
        self.port = self.server.getsockname()[1]
        self.errors = []
        self.passed = False
        self.ready = threading.Event()
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        peers = []
        try:
            deadline = time.monotonic() + 30
            while not self.stopped.is_set():
                try:
                    peer, _ = self.server.accept()
                except TimeoutError:
                    if not self.passed and time.monotonic() >= deadline:
                        raise TimeoutError('next prefill input did not progress')
                    continue
                peers.append(peer)
                peer.settimeout(5)
                message = json.loads(peer.makefile('rb').readline())
                if 'progress' in message:
                    assert message['progress'] == self.expected, (message, self.expected)
                    self.passed = True
                    self.ready.set()
                if self.passed:
                    for waiting in peers:
                        try:
                            waiting.sendall(b'1')
                        except OSError:
                            pass
                        waiting.close()
                    peers.clear()
        except Exception as exc:
            self.errors.append(repr(exc))
        finally:
            self.ready.set()
            for peer in peers:
                try:
                    peer.sendall(b'1')
                except OSError:
                    pass
                peer.close()
            self.server.close()

    def check(self):
        self.ready.wait(timeout=35)
        assert self.passed and not self.errors, ('prefill_progress', self.errors)

    def close(self):
        self.stopped.set()
        self.thread.join(timeout=6)


class Workload:
    def __init__(self, *, async_mode):
        from transformers import OPTConfig
        from vllm import LLM
        model = tempfile.mkdtemp(prefix='mp-behavior-model-')
        OPTConfig(architectures=["OPTForCausalLM"], vocab_size=1024, hidden_size=64, ffn_dim=128,
                  num_hidden_layers=4, num_attention_heads=4,
                  word_embed_proj_dim=64, max_position_embeddings=128).save_pretrained(model)
        os.environ['VLLM_ENABLE_V1_MULTIPROCESSING'] = '0'
        os.environ['VLLM_WORKER_MULTIPROC_METHOD'] = 'spawn'
        self.llm = LLM(model=model, load_format='dummy', skip_tokenizer_init=True,
            dtype='float16', pipeline_parallel_size=2, tensor_parallel_size=1,
            distributed_executor_backend='mp', async_scheduling=async_mode,
            enable_chunked_prefill=True, enable_prefix_caching=False,
            max_model_len=64, max_num_batched_tokens=64, max_num_seqs=16,
            long_prefill_token_threshold=8, kv_cache_memory_bytes=16 * 1024 * 1024,
            gpu_memory_utilization=0.1, enforce_eager=True, seed=42, disable_log_stats=True)
        core = self.llm.llm_engine.engine_core.engine_core
        self.scheduler = core.scheduler
        self.executor = core.model_executor
        self.executor.collective_rpc(install_probe)
        self.pending = []
        self.ids = []
        self.prompts = {}
        self.values = []
        self.positions = {}
        self.async_mode = async_mode

    def configure(self, **kwargs):
        return self.executor.collective_rpc(configure_probe,
            args=(self.ids, self.values), kwargs=kwargs)

    def admit(self, prompts, values, budgets=None):
        from vllm.v1.request import Request
        from vllm import SamplingParams
        self.ids = list(prompts)
        self.prompts = prompts
        self.values = values
        self.positions = dict.fromkeys(prompts, 0)
        self.configure(clear=True)
        for req_id, prompt in prompts.items():
            self.scheduler.add_request(Request(request_id=req_id, prompt_token_ids=prompt,
                sampling_params=SamplingParams(max_tokens=(budgets or {}).get(req_id, 12),
                    temperature=0, ignore_eos=True), pooling_params=None, eos_token_id=None))

    def submit(self):
        step = self.scheduler.schedule()
        for req_id, count in step.num_scheduled_tokens.items():
            self.positions[req_id] += count
        # Submit both operations through the candidate executor. Waiting on the
        # first execute before submitting sample could deadlock a valid Worker
        # that receives after forwarding activations.
        execution = self.executor.execute_model(step, non_block=True)
        # EngineCore's batch-queue path does not sample empty executions.
        output = (self.executor.sample_tokens(None, non_block=True)
                  if step.total_num_scheduled_tokens else execution)
        self.pending.append((step, execution, output))
        return step

    def collect(self):
        outputs = []
        for step, execution, future in self.pending:
            execution.result()
            output = future.result()
            if output is not None:
                self.scheduler.update_from_output(step, output)
                outputs.append(output)
        self.pending.clear()
        return outputs

    def reports(self, *, check=True):
        records = self.executor.collective_rpc(read_probe)
        assert {r['rank'] for r in records} == {0, 1}, records
        if check:
            assert all(not r['violations'] for r in records), ('handoff_host_wait', records)
        return records

    def finish(self):
        from vllm.v1.request import RequestStatus
        self.collect()
        self.configure(enabled=False)
        self.scheduler.finish_requests(self.ids, RequestStatus.FINISHED_ABORTED)
        self.submit()
        self.collect()
        assert self.scheduler.get_num_unfinished_requests() == 0

    def close(self):
        self.executor.shutdown()


def next_decode(work, name, count, *, warmup):
    ids = [f'{name}-{i}' for i in range(count)]
    prompts = {r: list(range(11, 51 if i == count - 1 else 19)) for i, r in enumerate(ids)}
    values = [101 + 101 * i for i in range(count)]
    work.admit(prompts, values)
    if warmup:
        work.submit(); work.collect()
    work.configure(enabled=True, clear=True)
    work.submit()
    work.configure(enabled=True, reorder=True)
    work.submit()
    records = work.reports()
    for rec in records:
        latest = rec['inputs'][-1]
        for req_id, value in zip(ids[:-1], values[:-1]):
            assert latest[req_id] == [value], ('next_input_token', name, rec['rank'], latest)
    outputs = work.collect()
    for output in outputs:
        assert dict(zip(output.req_ids, output.sampled_token_ids)) == {
            r: ([] if r == ids[-1] else [v]) for r, v in zip(ids, values)}
    work.finish()


def compaction(work):
    prompts = {'compact-finish': list(range(11, 19)), 'compact-long': list(range(41, 78))}
    work.admit(prompts, [311, 419], {'compact-finish': 2})
    work.submit(); work.collect()
    work.configure(enabled=True, clear=True)
    work.submit(); work.collect()
    while work.positions['compact-long'] < 37:
        start = work.positions['compact-long']
        step = work.submit()
        records = work.reports()
        for rec in records:
            expected = prompts['compact-long'][start:work.positions['compact-long']]
            assert rec['inputs'][-1] == {'compact-long': expected}, (
                'prompt_corrupted_after_compaction', rec['rank'], rec['inputs'][-1], expected)
        assert 'compact-finish' not in step.num_scheduled_tokens
        work.collect()
    work.finish()


def prefill_progress(work):
    prompts = {'prefill-a': list(range(11, 35)), 'prefill-b': list(range(41, 72))}
    work.admit(prompts, [313, 421])
    gate = PrefillGate({r: p[8:16] for r, p in prompts.items()})
    try:
        work.configure(enabled=True, clear=True, gate=gate.port)
        work.submit()
        work.submit()
        gate.check()
        work.reports()
        work.collect()
    finally:
        gate.close()
    work.finish()


def idle(work):
    work.admit({'idle-done': list(range(11, 19))}, [101], {'idle-done': 1})
    work.submit(); work.collect()
    assert work.scheduler.get_num_unfinished_requests() == 0
    work.configure(enabled=True, clear=True)
    assert not work.submit().num_scheduled_tokens
    work.collect()
    work.reports()


def external_inputs(work):
    for count in (2, 4):
        ids = [f'peer-row-{i}-{count}' for i in range(count)]
        work.admit({r: list(range(11, 35 if i == count - 1 else 19))
                    for i, r in enumerate(ids)}, [101] * count)
        work.configure(external=True, enabled=True)
        work.submit()
        # Keep unknown samples only on the last GPU. Reconfiguration must not
        # replace them with controller-owned values or collect scheduler output.
        def arm(wrapper):
            from worker_fixtures import PROBES
            PROBES[wrapper.worker].external_export = True
        work.executor.collective_rpc(arm)
        work.submit()
        work.reports()
        work.collect()
        work.finish()


def synchronous():
    work = Workload(async_mode=False)
    try:
        work.admit({'sync-left': list(range(11, 19)), 'sync-right': list(range(21, 29))}, [313, 421])
        work.submit(); work.collect()
        work.configure(reorder=True)
        work.submit()
        for rec in work.reports(check=False):
            assert rec['inputs'][-1] == {'sync-left': [313], 'sync-right': [421]}, rec
        work.collect(); work.finish()
    finally:
        work.close()


def run():
    # The supervisor's rank is a driver identity, not an mp worker rank.
    for key in ('RANK', 'LOCAL_RANK', 'WORLD_SIZE', 'MASTER_ADDR', 'MASTER_PORT'):
        os.environ.pop(key, None)
    timings = {}
    work = Workload(async_mode=True)
    try:
        for name, action in [('basic', lambda: next_decode(work, 'basic', 2, warmup=True)),
            ('reordered', lambda: next_decode(work, 'reordered', 3, warmup=True)),
            ('integrated', lambda: next_decode(work, 'integrated', 3, warmup=False)),
            ('compaction', lambda: compaction(work)),
            ('prefill_progress', lambda: prefill_progress(work)), ('idle', lambda: idle(work)),
            ('external_gpu_inputs', lambda: external_inputs(work))]:
            began = time.monotonic()
            action()
            timings[name] = round(time.monotonic() - began, 3)
            print(f'MP_BEHAVIOR=PASS case={name}', flush=True)
    finally:
        work.close()
    began = time.monotonic()
    synchronous()
    timings['synchronous'] = round(time.monotonic() - began, 3)
    print(json.dumps({'mp_behavior_timings': timings}), flush=True)
    return ['basic', 'reordered', 'integrated', 'compaction', 'prefill_progress', 'idle', 'synchronous']
