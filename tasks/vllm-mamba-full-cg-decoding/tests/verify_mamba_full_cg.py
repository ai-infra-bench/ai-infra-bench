#!/usr/bin/env python3
"""Unprivileged production client. The parent independently checks every result."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# The parent uses -I; only this child may load submitted Python code.
sys.path.insert(0, sys.argv[3] if len(sys.argv) == 4 else "/workspace/repo")
os.environ["VLLM_ENABLE_V1_MULTIPROCESSING"] = "0"
os.environ["VLLM_HOST_IP"] = "127.0.0.1"
os.environ["GLOO_SOCKET_IFNAME"] = "lo"


def main() -> None:
    request = json.loads(Path(sys.argv[1]).read_text())
    import torch
    from vllm import LLM, SamplingParams

    speculative = request["mode"] == "speculative"
    llm = LLM(
        model=request["model"],
        skip_tokenizer_init=True,
        dtype="float32",
        max_model_len=128,
        max_num_seqs=2,
        max_num_batched_tokens=request.get("token_budget", 16),
        kv_cache_memory_bytes=32 * 1024 * 1024,
        num_gpu_blocks_override=request.get("num_gpu_blocks"),
        enable_chunked_prefill=True,
        async_scheduling=False,
        enable_prefix_caching=request["cache"] == "all",
        mamba_cache_mode=request["cache"],
        enforce_eager=request.get("enforce_eager", False) or request["mode"] == "eager",
        speculative_config=(
            {"method": "ngram", "prompt_lookup_max": 3,
             "prompt_lookup_min": 1, "num_speculative_tokens": 2}
            if speculative else None
        ),
        compilation_config={
            "mode": 0,
            "cudagraph_mode": "FULL",
            "cudagraph_capture_sizes": [3, 6] if speculative else [1, 2],
        },
        max_logprobs=request["vocab_size"],
        disable_log_stats=not speculative,
    )
    batches = []
    profiler = torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU, torch.profiler.ProfilerActivity.CUDA])
    profiler.start()
    for batch in request["batches"]:
        results = llm.generate(
            [{"prompt_token_ids": prompt} for prompt in batch],
            SamplingParams(temperature=0, max_tokens=request["steps"],
                           ignore_eos=True, logprobs=request["vocab_size"]),
            use_tqdm=False,
        )
        batches.append([
            {"prompt": result.prompt_token_ids,
             "tokens": list(result.outputs[0].token_ids),
             "logprobs": [
                 [step[token].logprob for token in range(request["vocab_size"])]
                 for step in result.outputs[0].logprobs
             ]}
            for result in results
        ])
    profiler.stop()
    launches = sum(event.count for event in profiler.key_averages()
                   if "cudaGraphLaunch" in event.key or "cuGraphLaunch" in event.key)
    accepted = (sum(metric.value for metric in llm.get_metrics()
                    if metric.name == "vllm:spec_decode_num_accepted_tokens")
                if speculative else None)
    Path(sys.argv[2]).write_text(json.dumps(
        {"batches": batches, "graph_launches": launches, "accepted_tokens": accepted}, allow_nan=False))


if __name__ == "__main__":
    main()
