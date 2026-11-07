#!/usr/bin/env python3
"""Production generation client; numeric and CUDA observations are checked outside it."""
from __future__ import annotations

import json
import os
import signal
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[3] if len(sys.argv) == 4 else "/workspace/repo")
os.environ.update(VLLM_ENABLE_V1_MULTIPROCESSING="0", VLLM_HOST_IP="127.0.0.1", GLOO_SOCKET_IFNAME="lo")


def main() -> None:
    request = json.loads(Path(sys.argv[1]).read_text())
    from vllm import LLM, SamplingParams

    speculative = request.get("speculative", False)
    options = dict(
        model=request["model"], skip_tokenizer_init=True, dtype="float32",
        max_model_len=request.get("max_model_len", 128),
        max_num_seqs=request.get("max_num_seqs", 2),
        max_num_batched_tokens=request.get("token_budget", 16),
        kv_cache_memory_bytes=32 * 1024 * 1024,
        num_gpu_blocks_override=request.get("num_gpu_blocks"),
        enable_chunked_prefill=True, async_scheduling=False,
        enable_prefix_caching=request["cache"] == "all", mamba_cache_mode=request["cache"],
        enforce_eager=request.get("eager", False),
        speculative_config={"method": "ngram", "prompt_lookup_min": 2,
                            "prompt_lookup_max": 3, "num_speculative_tokens": 2}
        if speculative else None,
        compilation_config={"mode": 0, "cudagraph_mode": "FULL",
                            "cudagraph_capture_sizes": request["captures"]},
        max_logprobs=request["vocab_size"], disable_log_stats=not speculative,
    )
    if request.get("mamba_block_size") is not None:
        options["mamba_block_size"] = request["mamba_block_size"]
    llm = LLM(**options)

    def sampling(steps):
        return SamplingParams(temperature=0, max_tokens=steps, ignore_eos=True,
                              logprobs=request["vocab_size"])

    def serialize(result):
        output = result.outputs[0]
        return {"prompt": result.prompt_token_ids, "tokens": list(output.token_ids),
                "logprobs": [[row[token].logprob for token in range(request["vocab_size"])]
                             for row in output.logprobs]}

    if request.get("observe_gpu"):
        os.kill(os.getpid(), signal.SIGUSR1)
    batches, cached_tokens = [], []
    for batch in request["batches"]:
        results = llm.generate([{"prompt_token_ids": prompt} for prompt in batch],
                               sampling(request["steps"]), use_tqdm=False)
        batches.append([serialize(result) for result in results])
        cached_tokens.extend(getattr(result, "num_cached_tokens", 0) for result in results)

    if request.get("lifecycle"):
        prompts = request["lifecycle"]["prompts"]
        ids = llm.enqueue([{"prompt_token_ids": prompt} for prompt in prompts],
                          sampling(32), use_tqdm=False)

        def advance(count):
            for _ in range(count):
                llm.llm_engine.step()

        advance(8)
        long_id = llm.enqueue([{"prompt_token_ids": request["lifecycle"]["long_prompt"]}],
                              sampling(16), use_tqdm=False)[0]
        advance(1)
        llm.llm_engine.abort_request([long_id], internal=True)
        advance(3)
        llm.llm_engine.abort_request([ids[0]], internal=True)
        survivors = llm.wait_for_completion(use_tqdm=False)
        rows = {tuple(result.prompt_token_ids): serialize(result) for result in survivors}
        batches.append([rows[tuple(prompt)] for prompt in prompts[1:]])

    if request.get("observe_gpu"):
        os.kill(os.getpid(), signal.SIGUSR2)
    accepted = (sum(metric.value for metric in llm.get_metrics()
                    if metric.name == "vllm:spec_decode_num_accepted_tokens")
                if speculative else None)
    Path(sys.argv[2]).write_text(json.dumps(
        {"batches": batches, "accepted_tokens": accepted, "cached_tokens": cached_tokens},
        allow_nan=False))


if __name__ == "__main__":
    main()
