from __future__ import annotations

import torch


def run_compile_trace(batch_sizes: tuple[int, ...], *, vocab_size: int = 32) -> dict:
    from vllm.v1.sample.ops.logprobs import batched_count_greater_than
    from vllm.v1.sample.sampler import Sampler
    import vllm.v1.sample.ops.logprobs as logprobs_module
    import vllm.v1.sample.sampler as sampler_module

    torch._dynamo.reset()
    compile_count = 0

    def counting_backend(gm, _example_inputs):
        nonlocal compile_count
        compile_count += 1
        return gm.forward

    unwrapped = batched_count_greater_than._torchdynamo_orig_callable
    patched = torch.compile(unwrapped, backend=counting_backend)
    original_logprobs = logprobs_module.batched_count_greater_than
    original_sampler = sampler_module.batched_count_greater_than
    logprobs_module.batched_count_greater_than = patched
    sampler_module.batched_count_greater_than = patched
    counts = []
    outputs = []
    try:
        for index, batch_size in enumerate(batch_sizes):
            generator = torch.Generator().manual_seed(1000 + index)
            values = torch.randn(batch_size, vocab_size, generator=generator)
            token_ids = torch.arange(batch_size, dtype=torch.int64) % vocab_size
            output = Sampler.gather_logprobs(values, 3, token_ids)
            counts.append(compile_count)
            outputs.append(output)
    finally:
        logprobs_module.batched_count_greater_than = original_logprobs
        sampler_module.batched_count_greater_than = original_sampler
        torch._dynamo.reset()
    return {"batch_sizes": list(batch_sizes), "compile_counts": counts, "outputs": outputs}


def unwrapped_count(x: torch.Tensor, values: torch.Tensor) -> torch.Tensor:
    from vllm.v1.sample.ops.logprobs import batched_count_greater_than

    return batched_count_greater_than._torchdynamo_orig_callable(x, values)
