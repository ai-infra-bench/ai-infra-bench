#!/usr/bin/env python3
"""Candidate-side adapter. Expectations, timing and verdicts live in the parent."""
import contextlib
import copy
from concurrent.futures import Future
import hashlib
import json
from pathlib import Path
import socket
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixtures as f


def serve(fd, meter):
    channel = socket.socket(fileno=fd)
    from nixl_io import install
    install()
    f.load_candidate()
    from vllm.v1.engine.core import EngineCore

    class Adapter:
        def __init__(self, model_dir):
            self.model_dir = model_dir
            self.scheduler = None
            self.matches = {}
            self.grammars = {}
            self.last = None
            self.calls = 0
            self.ready = set()
            self.tokens = {}
            self.params = {}
            self.auto_ready = False

        def reset(self, options):
            self.matches = {}
            self.grammars = {}
            self.last = None
            self.auto_ready = False
            self.scheduler = f.create_scheduler(
                self.model_dir, options.get('capacity', 4),
                max_num_batched_tokens=options.get('budget', 8192),
                use_connector=options.get('connector', True),
                num_blocks=options.get('blocks'),
            )
            if self.scheduler.connector is not None:
                self.scheduler.connector.get_num_new_matched_tokens = self.match
            self.engine = SimpleNamespace(
                scheduler=self.scheduler, model_executor=self,
                log_error_detail=lambda *a: contextlib.nullcontext(),
                log_iteration_details=lambda *a: contextlib.nullcontext(),
                _process_aborts_queue=lambda: None,
            )
            return self.state()

        def match(self, request, count):
            return (self.matches[request.request_id], True) if request.request_id in self.matches else (0, False)

        def add(self, items):
            for item in items:
                identity = item['id']
                max_tokens = item.get('max_tokens', 3)
                if item.get('grammar'):
                    params = f.SamplingParams(max_tokens=max_tokens, ignore_eos=True,
                        structured_outputs=f.StructuredOutputsParams(choice=['yes', 'no']))
                    params.update_from_generation_config({}, 50256)
                else:
                    if max_tokens not in self.params:
                        params = f.SamplingParams(max_tokens=max_tokens, ignore_eos=True)
                        params.update_from_generation_config({}, 50256)
                        self.params[max_tokens] = params
                    params = self.params[max_tokens]
                if not f._HASH_INITIALIZED:
                    f.init_none_hash(f.sha256)
                    f._HASH_INITIALIZED = True
                request = f.Request(request_id=identity,
                    prompt_token_ids=[item.get('value', 1)] * item.get('prompt', 10),
                    sampling_params=params, pooling_params=None,
                    block_hasher=f.get_request_block_hasher(16, f.sha256))
                if item.get('stream'):
                    request.resumable = True
                if item.get('grammar'):
                    future = Future()
                    request.structured_output_request.grammar = future
                    self.grammars[identity] = future
                if item.get('remote'):
                    self.matches[identity] = item.get('cached', 8)
                self.scheduler.add_request(request)
            return self.state()

        def execute_model(self, scheduled, **kwargs):
            self.calls += 1
            self.last = scheduled
            req_ids = list(scheduled.num_scheduled_tokens)
            samples = []
            for identity in req_ids:
                request = self.scheduler.requests[identity]
                complete_prompt = request.num_computed_tokens >= request.num_prompt_tokens
                samples.append([self.tokens.get(identity, 100)] if complete_prompt else [])
            if self.auto_ready and self.scheduler.connector is not None:
                self.ready.update(self.scheduler.connector.started_receives)
            output = f.ModelRunnerOutput(req_ids=req_ids,
                req_id_to_index={identity: i for i, identity in enumerate(req_ids)},
                sampled_token_ids=samples,
                kv_connector_output=(f.KVConnectorOutput(finished_recving=self.ready) if self.ready else None))
            future = Future()
            future.set_result(output)
            return future

        def state(self):
            return {'counts': list(self.scheduler.get_request_counts()),
                    'unfinished': self.scheduler.get_num_unfinished_requests(),
                    'has_requests': self.scheduler.has_requests()}

        def tick(self, ready=(), tokens=None, auto_ready=False):
            self.auto_ready = auto_ready
            self.ready = set(ready)
            self.tokens = tokens or {}
            self.last = None
            self.calls = 0
            outputs, ran = EngineCore.step(self.engine)
            rows = [[output.request_id, output.new_token_ids, output.finish_reason is not None]
                    for group in outputs.values() for output in group.outputs]
            scheduled = self.last
            result = self.state()
            result.update({'admitted': [r.req_id for r in scheduled.scheduled_new_reqs] if scheduled else [],
                           'scheduled': dict(scheduled.num_scheduled_tokens) if scheduled else {},
                           'outputs': rows, 'executor_calls': self.calls})
            return result

        def idle(self, rounds):
            count = 0
            outputs = 0
            for _ in range(rounds):
                # Measure the target scheduler tick; the independent EngineCore
                # lifecycle cases cover its admission/has_requests caller.
                result = self.scheduler.schedule()
                count += result.total_num_scheduled_tokens
                outputs += len(result.scheduled_new_reqs)
            return self.state() | {'scheduled_tokens': count, 'admitted': outputs, 'rounds': rounds}

        def churn(self, start, count, salt, remote):
            digest = hashlib.sha256()
            returned = terminals = 0
            for index in range(start, start + count):
                identity = f'{salt}-{index}'
                token = 100 + (index * 17 + salt) % 49000
                self.add([{'id': identity, 'prompt': 32 + index % 33,
                           'max_tokens': 1, 'remote': remote, 'cached': 16,
                           'value': 1 + index % 127}])
                self.tokens = {identity: token}
                for ready in ((), (identity,), ()) if remote else ((),):
                    self.ready = set(ready)
                    outputs, _ = EngineCore.step(self.engine)
                    for group in outputs.values():
                        for output in group.outputs:
                            row = [output.request_id, output.new_token_ids, output.finish_reason is not None]
                            digest.update(json.dumps(row, separators=(',', ':')).encode() + b'\n')
                            returned += len(row[1])
                            terminals += bool(row[2])
                self.matches.pop(identity, None)
            for _ in range(16):
                step = self.tick()
                for row in step['outputs']:
                    digest.update(json.dumps(row, separators=(',', ':')).encode() + b'\n')
                    returned += len(row[1])
                    terminals += bool(row[2])
            return self.state() | {'digest': digest.hexdigest(), 'tokens': returned, 'terminals': terminals}

        def dispatch(self, command):
            operation = command['op']
            if operation == 'reset': return self.reset(command)
            if operation == 'add': return self.add(command['items'])
            if operation == 'tick': return self.tick(command.get('ready', ()), command.get('tokens'), command.get('auto_ready', False))
            if operation == 'plan':
                planned = self.scheduler.schedule()
                return self.state() | {'admitted': [r.req_id for r in planned.scheduled_new_reqs],
                                       'scheduled': dict(planned.num_scheduled_tokens)}
            if operation == 'idle': return self.idle(command['rounds'])
            if operation == 'churn':
                return self.churn(command['start'], command['count'], command['salt'], command['remote'])
            if operation == 'abort':
                self.scheduler.finish_requests(command['ids'], f.RequestStatus.FINISHED_ABORTED)
                return self.state()
            if operation == 'grammar':
                self.grammars.pop(command['id']).set_result(object())
                return self.state()
            if operation == 'local':
                for identity in command['ids']: self.matches.pop(identity, None)
                return self.state()
            if operation == 'preempt':
                return {'reset': self.scheduler.reset_prefix_cache(reset_running_requests=True)} | self.state()
            if operation == 'nixl':
                from nixl_behavior import exercise
                return {'observations': exercise(self.model_dir)}
            if operation == 'state': return self.state()
            raise ValueError('unknown adapter operation')

    with tempfile.TemporaryDirectory(prefix='remote-kv-input-') as tmp:
        (Path(tmp) / 'config.json').write_text(json.dumps(f.MODEL_CONFIG))
        adapter = Adapter(tmp)
        channel.send(json.dumps({'ready': True}).encode())
        while True:
            packet = channel.recv(65536)
            if not packet: break
            command = json.loads(packet)
            if command['op'] == 'snapshot':
                meter.snapshot(bytes.fromhex(command['nonce']))
                continue
            if command['op'] == 'quit': break
            value = adapter.dispatch(command)
            channel.send(json.dumps(value, separators=(',', ':')).encode())
    channel.close()


if __name__ == '__main__':
    serve(_rpc_fd, _meter)
