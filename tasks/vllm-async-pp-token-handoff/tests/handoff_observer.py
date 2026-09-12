"""Observe tensor device flow and explicit host waits during sampling.

TorchFunctionMode also runs under the production inference_mode decorator,
where TorchDispatchMode alone does not see transfers. Python C-call profiling
observes actual Stream/Event/device synchronize calls without counting internal
NCCL initialization waits. This is behavioral instrumentation, not a security
boundary. Operations execute normally; rejection occurs after both peers return.
"""
from contextlib import contextmanager
import sys

import torch
from torch.overrides import TorchFunctionMode


class HandoffObserver(TorchFunctionMode):
    def __init__(self, *, prior_event_ids=(), check_object_communication=True):
        super().__init__()
        self.transfers = []
        self.violations = []
        self.prior_event_ids = set(prior_event_ids)
        self.recorded_event_ids = set()
        self.active = True
        self.check_object_communication = check_object_communication

    def _transfer(self, op, non_blocking):
        record = {"kind": "device_to_host_copy", "op": op,
                  "non_blocking": bool(non_blocking)}
        self.transfers.append(record)
        if not non_blocking:
            self.violations.append(record)

    def __torch_function__(self, func, types, args=(), kwargs=None):
        kwargs = kwargs or {}
        if not self.active:
            return func(*args, **kwargs)
        source = args[0] if args else None
        name = getattr(func, "__name__", str(func))
        gpu_source = isinstance(source, torch.Tensor) and source.is_cuda
        reads = {"item", "tolist", "numpy", "__bool__", "__int__",
                 "__float__", "__index__", "is_nonzero", "_local_scalar_dense.default"}
        if gpu_source and name in reads:
            self.violations.append({"kind": "cuda_host_read", "op": name})
        if name in ("copy_", "copy_.default"):
            src = args[1] if len(args) > 1 else kwargs.get("src")
            if (isinstance(src, torch.Tensor) and src.is_cuda
                    and isinstance(source, torch.Tensor) and source.device.type == "cpu"):
                non_blocking = args[2] if len(args) > 2 else kwargs.get("non_blocking", False)
                self._transfer(name, non_blocking)
        result = func(*args, **kwargs)
        # *_like / new_empty allocations can use a CUDA tensor's shape while
        # creating CPU storage without reading any CUDA data. Only actual
        # conversion operations move the source tensor's values to the host.
        conversions = {"cpu", "to", "type", "type_as", "_to_copy.default",
                       "as_tensor", "asarray", "tensor"}
        if (gpu_source and name in conversions and isinstance(result, torch.Tensor)
                and result.device.type == "cpu"):
            if name == "to":
                options = {k: v for k, v in kwargs.items() if k != "copy"}
                non_blocking = torch._C._nn._parse_to(*args[1:], **options)[2]
            elif name in ("type", "type_as"):
                non_blocking = kwargs.get("non_blocking", args[2] if len(args) > 2 else False)
            else:
                non_blocking = kwargs.get("non_blocking", False)
            self._transfer(name, non_blocking)
        return result

    @contextmanager
    def pause(self):
        """Exclude task-owned GPU observations; candidate calls stay observed."""
        active = self.active
        self.active = False
        try:
            with torch.profiler.record_function('async_pp_test_observation'):
                yield
        finally:
            self.active = active

    @contextmanager
    def observe(self):
        previous = sys.getprofile()
        prior_event_scopes = []
        import torch.distributed as dist
        originals = {}
        for name in ('broadcast_object_list', 'all_gather_object', 'gather_object',
                     'scatter_object_list', 'send_object_list', 'recv_object_list'):
            original = getattr(dist, name)
            originals[name] = original
            def wrapped(*args, _name=name, _original=original, **kwargs):
                if self.active and self.check_object_communication:
                    self.violations.append({'kind': 'cpu_object_communication', 'op': _name})
                return _original(*args, **kwargs)
            setattr(dist, name, wrapped)

        def observe_call(frame, event, function):
            if not self.active:
                return
            if event == "c_call":
                name = getattr(function, "__name__", "")
                owner = getattr(function, "__self__", None)
                device_wait = (name == "_cuda_synchronize"
                               and getattr(function, "__module__", "") == "torch._C")
                object_wait = (name == "synchronize" and isinstance(
                    owner, (torch.Stream, torch.Event, torch.cuda.Stream, torch.cuda.Event)))
                if object_wait:
                    device = owner.device
                    object_wait = device is not None and device.type == "cuda"
                if name == 'record' and isinstance(owner, (torch.Event, torch.cuda.Event)):
                    self.recorded_event_ids.add(id(owner))
                    self.prior_event_ids.discard(id(owner))
                if object_wait and id(owner) in self.prior_event_ids:
                    # This event was already recorded before sampling and has
                    # not been re-recorded since. It cannot depend on new tokens.
                    scope = torch.profiler.record_function('async_pp_prior_input_event')
                    scope.__enter__()
                    prior_event_scopes.append((function, scope))
                    object_wait = False
                if device_wait or object_wait:
                    self.violations.append({"kind": "cuda_host_wait", "op": name})
            elif event in ('c_return', 'c_exception') and prior_event_scopes:
                function_owner, scope = prior_event_scopes[-1]
                if function == function_owner:
                    prior_event_scopes.pop()
                    scope.__exit__(None, None, None)
            if previous is not None:
                previous(frame, event, function)

        # CPU activity captures CUDA runtime calls made inside ATen operators,
        # including implicit waits invisible to Python's C-call profiler.
        with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU]) as trace:
            with self, torch.profiler.record_function("async_pp_handoff_boundary"):
                sys.setprofile(observe_call)
                try:
                    yield self
                finally:
                    sys.setprofile(previous)
                    for name, original in originals.items():
                        setattr(dist, name, original)
        for event in trace.events():
            if event.name not in ("cudaStreamSynchronize", "cudaDeviceSynchronize",
                                  "cudaEventSynchronize", "cuStreamSynchronize",
                                  "cuCtxSynchronize", "cuEventSynchronize"):
                continue
            parent = event.cpu_parent
            prior_input_event = False
            while parent is not None and parent.name != "async_pp_handoff_boundary":
                prior_input_event |= parent.name in ('async_pp_prior_input_event', 'async_pp_test_observation')
                parent = parent.cpu_parent
            if parent is not None and not prior_input_event:
                self.violations.append({"kind": "cuda_runtime_host_wait", "op": event.name})
