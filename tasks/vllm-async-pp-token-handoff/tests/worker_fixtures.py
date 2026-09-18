"""Task-owned probes installed on real mp workers through collective_rpc.

Construction, device setup, model loading, KV setup, activation transport and
execute/sample dispatch belong to vLLM. Probes control logits and observe model
forward inputs; they never call a candidate token helper or seed runner state.
"""
from contextlib import nullcontext
from weakref import WeakKeyDictionary

import torch

from handoff_observer import HandoffObserver

PROBES = WeakKeyDictionary()


class WorkerProbe:
    def __init__(self, worker):
        self.worker = worker
        self.runner = worker.model_runner
        self.rank = worker.rank
        self.records = []
        self.violations = []
        self.sample_ids = []
        self.samples = None
        self.enabled = False
        self.step = None
        self.prior_events = set()
        self.observer = None
        self.forward_count = 0
        self.gate = None
        self.external = None
        self.external_export = False
        model = worker.get_model()
        forward = model.forward
        logits = model.compute_logits
        execute = worker.execute_model
        sample = worker.sample_tokens

        def observed_forward(*args, **kwargs):
            if self.observer is not None:
                # Events recorded before this model input cannot depend on
                # samples produced by this forward. A later record invalidates
                # that exemption, even when the same event object is reused.
                self.observer.prior_event_ids.update(self.observer.recorded_event_ids)
            inputs = kwargs['input_ids'] if 'input_ids' in kwargs else args[0]
            if self.step is not None:
                ids = tuple(self.runner.input_batch.req_ids)
                offset = 0
                record = {}
                for req_id in ids:
                    count = self.step.num_scheduled_tokens[req_id]
                    record[req_id] = inputs[offset:offset + count].clone()
                    offset += count
                self.records.append(record)
                self.forward_count += 1
                if self.gate and self.rank == 0 and self.forward_count == 2:
                    # This is a test observation, outside candidate handoff
                    # checking. It proves GPU progress, not just host enqueue.
                    with self.observer.pause() if self.observer else nullcontext():
                        actual = {r: t.cpu().tolist() for r, t in record.items()}
                        import socket, json
                        with socket.create_connection(('127.0.0.1', self.gate), timeout=40) as peer:
                            peer.sendall(json.dumps({'progress': actual}).encode() + b'\n')
                if self.external_export and self.rank == 0:
                    with self.observer.pause() if self.observer else nullcontext():
                        _, group = self.external
                        wanted = self.sample_ids[:-1][::-1]
                        payload = torch.cat([record[r] for r in wanted]).to(torch.int32)
                        group.send([payload], 0, 0).wait()
                    self.external_export = False
            return forward(*args, **kwargs)

        def controlled_logits(hidden, *args, **kwargs):
            if self.gate and self.rank == 1 and self.forward_count == 1:
                # Hold production of otherwise discarded samples, wherever the
                # candidate calls logits. Skipping that work entirely is valid.
                import socket
                with socket.create_connection(('127.0.0.1', self.gate), timeout=40) as peer:
                    peer.sendall(b'{"sampling": true}\n')
                    assert peer.recv(1) == b'1', 'prefill gate failed'
            if self.samples is None:
                return logits(hidden, *args, **kwargs)
            rows = [self.sample_ids.index(r) for r in self.runner.input_batch.req_ids[:len(hidden)]]
            indices = torch.tensor(rows, pin_memory=True).to(hidden.device, non_blocking=True)
            selected = self.samples.index_select(0, indices)
            scores = torch.full((len(hidden), 1024), -100., device=hidden.device)
            scores.scatter_(1, selected.to(torch.int64).reshape(-1, 1), 100.)
            return scores

        def observed_execute(step, *args, **kwargs):
            self.step = step
            return self.observe_call(execute, step, *args,
                _no_samples=not step.total_num_scheduled_tokens,
                _check_objects=False, **kwargs)

        def observed_sample(*args, **kwargs):
            result = self.observe_call(sample, *args, **kwargs)
            return result

        model.forward = observed_forward
        model.compute_logits = controlled_logits
        worker.execute_model = observed_execute
        worker.sample_tokens = observed_sample

    def observe_call(self, method, *args, _no_samples=False, _check_objects=True, **kwargs):
        # Execute includes CPU activation metadata, whose protocol is not part
        # of the task. Observe CUDA transfers/waits throughout Worker execution;
        # object communication is checked where new samples are produced.
        observer = HandoffObserver(prior_event_ids=self.prior_events,
            check_object_communication=_check_objects)
        self.observer = observer
        try:
            with observer.observe():
                result = method(*args, **kwargs)
            if _no_samples:
                # An empty round can record an input-buffer event on exit, but
                # produces no new samples. Only subsequent calls may reuse it;
                # waits within the empty round were still observed above.
                observer.prior_event_ids.update(observer.recorded_event_ids)
        finally:
            self.observer = None
            self.prior_events = set(observer.prior_event_ids)
            if self.enabled:
                self.violations.extend(observer.violations)
        return result


def install_probe(wrapper):
    worker = wrapper.worker
    PROBES[worker] = WorkerProbe(worker)
    # Warm the allowed NCCL collective and P2P mechanisms outside observation.
    import torch.distributed as dist
    from vllm.distributed.parallel_state import get_pp_group
    group = get_pp_group()
    warm = torch.zeros(1, dtype=torch.int32, device=worker.device)
    dist.broadcast(warm, src=group.last_rank, group=group.device_group)
    if group.is_last_rank:
        dist.send(warm, dst=group.first_rank, group=group.device_group)
    else:
        dist.recv(warm, src=group.last_rank, group=group.device_group)
    torch.cuda.synchronize()
    return {'rank': worker.rank, 'uid': __import__('os').getuid()}


def configure_probe(wrapper, ids, values, *, enabled=False, clear=False,
                    reorder=False, gate=None, external=False, export=False):
    probe = PROBES[wrapper.worker]
    probe.sample_ids = list(ids)
    probe.enabled = enabled
    probe.gate = gate
    if clear:
        probe.records.clear()
        probe.violations.clear()
        probe.forward_count = 0
        probe.step = None
    if external:
        from trusted_transport import observation_group
        if probe.external is None:
            probe.external = observation_group(probe.rank)
        if probe.rank == 1:
            probe.samples = torch.empty(len(ids), dtype=torch.int32, device=probe.worker.device)
            probe.external[1].recv([probe.samples], 0, 0).wait()
        else:
            probe.samples = None
    else:
        probe.samples = torch.tensor(values, device=probe.worker.device) if probe.rank == 1 else None
    if reorder:
        batch = probe.runner.input_batch
        for target, req_id in enumerate(reversed(ids)):
            if req_id in batch.req_id_to_index:
                index = batch.req_id_to_index[req_id]
                if index != target:
                    batch.swap_states(target, index)
    probe.external_export = export
    return probe.rank


def read_probe(wrapper):
    probe = PROBES[wrapper.worker]
    return {'rank': probe.rank,
            'inputs': [{r: t.cpu().tolist() for r, t in row.items()} for row in probe.records],
            'violations': list(probe.violations)}
