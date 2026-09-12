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
    def __init__(self):
        super().__init__()
        self.transfers = []
        self.violations = []

    def _transfer(self, op, non_blocking):
        record = {"kind": "device_to_host_copy", "op": op,
                  "non_blocking": bool(non_blocking)}
        self.transfers.append(record)
        if not non_blocking:
            self.violations.append(record)

    def __torch_function__(self, func, types, args=(), kwargs=None):
        kwargs = kwargs or {}
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
    def observe(self):
        previous = sys.getprofile()

        def observe_call(frame, event, function):
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
                if device_wait or object_wait:
                    self.violations.append({"kind": "cuda_host_wait", "op": name})
            if previous is not None:
                previous(frame, event, function)

        with self:
            sys.setprofile(observe_call)
            try:
                yield self
            finally:
                sys.setprofile(previous)
