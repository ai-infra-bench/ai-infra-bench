from __future__ import annotations

# Curator-only runtime smoke for the CPU encoder-cache-accounting image
# (task.toml: environment_profile = "cpu", gpus = 0, accelerator = "CPU").
# It confirms the candidate vLLM and its native extension resolve from /app and
# that the image imports on CPU. This task needs no GPU, so it asserts CPU
# semantics (CUDA is not required and not present) rather than requiring a GPU.

import importlib.util
import json
from pathlib import Path

import torch
import vllm


root = Path("/app")
source = Path(vllm.__file__).resolve()
native_spec = importlib.util.find_spec("vllm._C")
assert source.is_relative_to(root), source
assert native_spec is not None and native_spec.origin is not None
native = Path(native_spec.origin).resolve()
assert native.is_relative_to(root), native
assert torch.__version__.startswith("2.9."), torch.__version__
# This is a CPU task: no accelerator is provisioned, so CUDA must NOT be
# required at import/run time. Assert the CPU condition rather than a GPU.
assert not torch.cuda.is_available(), (
    "CPU task unexpectedly sees a CUDA device; environment_profile is 'cpu'"
)

print(
    json.dumps(
        {
            "candidate_source": str(source),
            "native_extension": str(native),
            "torch": torch.__version__,
            "torch_cuda_build": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(),
            "device": "cpu",
        },
        sort_keys=True,
    )
)
