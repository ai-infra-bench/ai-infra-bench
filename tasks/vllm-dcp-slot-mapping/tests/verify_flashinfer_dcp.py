"""Real local FlashInfer planning, decode kernels and CUDA replay.

The config and CommonAttentionMetadata are stable production boundaries.
The cache represents a completed prefill; Q=K=0 makes the local attention
mean independently calculable. Only distributed rank identity is substituted.
This is local-rank coverage, not an NCCL or full-model inference test.
"""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import torch


def check_flashinfer(*, rank, graph, block_size, interleave=2, dcp_size=2):
    from vllm.config import (CacheConfig, CompilationConfig, ModelConfig,
        ParallelConfig, SchedulerConfig, VllmConfig, set_current_vllm_config)
    from vllm.config.compilation import CUDAGraphMode
    from vllm.v1.kv_cache_interface import FullAttentionSpec
    from vllm.v1.attention.backend import CommonAttentionMetadata
    from vllm.v1.attention.backends import flashinfer
    from vllm.model_executor.layers.attention.attention import Attention

    with tempfile.TemporaryDirectory(prefix="attention-model-") as directory:
        Path(directory, "config.json").write_text(json.dumps({
            "model_type": "qwen3", "architectures": ["Qwen3ForCausalLM"],
            "hidden_size": 512, "intermediate_size": 1024,
            "num_hidden_layers": 2, "num_attention_heads": 4,
            "num_key_value_heads": 1, "head_dim": 128,
            "vocab_size": 256, "max_position_embeddings": 128}))
        cfg = VllmConfig(
            model_config=ModelConfig(model=directory, dtype="float16",
                max_model_len=128, skip_tokenizer_init=True, enforce_eager=not graph),
            cache_config=CacheConfig(block_size=block_size, cache_dtype="auto"),
            parallel_config=ParallelConfig(tensor_parallel_size=dcp_size,
                decode_context_parallel_size=dcp_size,
                distributed_executor_backend="mp",
                cp_kv_cache_interleave_size=interleave),
            scheduler_config=SchedulerConfig(max_num_batched_tokens=128,
                max_num_seqs=2, max_model_len=128, async_scheduling=False,
                is_encoder_decoder=False),
            compilation_config=CompilationConfig(mode=0,
                cudagraph_mode=(CUDAGraphMode.FULL_DECODE_ONLY if graph
                                else CUDAGraphMode.NONE),
                cudagraph_capture_sizes=[1, 2]))
        # Select the supported native FlashInfer path on the declared hardware.
        cfg.attention_config.use_trtllm_attention = False
        layer = "model.layers.0.self_attn.attn"
        with set_current_vllm_config(cfg), patch.object(flashinfer, "get_dcp_group",
                return_value=SimpleNamespace(world_size=dcp_size, rank_in_group=rank)):
            Attention(num_heads=4 // dcp_size, head_size=128, scale=128**-0.5,
                num_kv_heads=1, cache_config=cfg.cache_config, prefix=layer,
                attn_backend=flashinfer.FlashInferBackend)
            spec = FullAttentionSpec(block_size=block_size, num_kv_heads=1,
                                     head_size=128, dtype=torch.float16)
            builder = flashinfer.FlashInferMetadataBuilder(spec, [layer], cfg,
                                                          torch.device("cuda"))
            # Three disjoint caches; request C replaces A, and row order changes.
            bases = {"a": 1, "b": 10, "c": 20}
            offsets = {"a": 0, "b": 100, "c": 200}
            cache = torch.zeros((32, 2, block_size, 1, 128),
                                dtype=torch.float16, device="cuda")
            owned = [p for p in range(128)
                     if (p // interleave) % dcp_size == rank]
            for req, base in bases.items():
                for local, pos in enumerate(owned):
                    cache[base + local // block_size, 1, local % block_size, 0] = (
                        pos + 1 + offsets[req]) / 512
            if flashinfer.get_kv_cache_layout() == "HND":
                cache = cache.permute(0, 1, 3, 2, 4).contiguous()
            q = torch.zeros((2, 4, 128), dtype=torch.float16, device="cuda")
            query_cpu = torch.tensor([0, 1, 2], dtype=torch.int32)
            query_gpu = query_cpu.to("cuda")
            lengths_gpu = torch.empty(2, dtype=torch.int32, device="cuda")
            table = torch.empty((2, 8), dtype=torch.int32, device="cuda")
            boundary = block_size * dcp_size
            plans = [(("a", "b"), (boundary - 3, boundary - 1)),
                     (("a", "b"), (boundary - 2, boundary)),
                     (("b", "a"), (boundary + 1, boundary - 1)),
                     (("b", "c"), (boundary + 2, 7)),
                     (("c", "b"), (8, boundary + 3))]
            captured = None
            rows = []
            for requests, lengths in plans:
                lengths_gpu.copy_(torch.tensor(lengths, dtype=torch.int32))
                table.copy_(torch.tensor([list(range(bases[r], bases[r]+8))
                                          for r in requests], dtype=torch.int32))
                slots = []
                for req, length in zip(requests, lengths):
                    pos = length - 1
                    if (pos // interleave) % dcp_size != rank:
                        slots.append(-1)
                    else:
                        local = sum((p // interleave) % dcp_size == rank
                                    for p in range(pos))
                        slots.append((bases[req] + local // block_size) * block_size
                                     + local % block_size)
                common = CommonAttentionMetadata(query_start_loc=query_gpu,
                    query_start_loc_cpu=query_cpu, seq_lens=lengths_gpu,
                    num_reqs=2, num_actual_tokens=2, max_query_len=1,
                    max_seq_len=max(lengths), block_table_tensor=table,
                    slot_mapping=torch.tensor(slots, dtype=torch.int64, device="cuda"),
                    causal=True, _seq_lens_cpu=torch.tensor(lengths, dtype=torch.int32))
                metadata = builder.build(0, common)
                wrapper = metadata.decode.wrapper
                if graph and captured is None:
                    stream = torch.cuda.Stream()
                    stream.wait_stream(torch.cuda.current_stream())
                    with torch.cuda.stream(stream):
                        wrapper.run(q, cache)
                    torch.cuda.current_stream().wait_stream(stream)
                    captured = torch.cuda.CUDAGraph()
                    with torch.cuda.graph(captured):
                        out = wrapper.run(q, cache)
                elif not graph:
                    out = wrapper.run(q, cache)
                if graph:
                    captured.replay()
                torch.cuda.synchronize()
                expected = []
                for req, length in zip(requests, lengths):
                    positions = [p for p in range(length)
                                 if (p // interleave) % dcp_size == rank]
                    expected.append(sum((p + 1 + offsets[req]) / 512
                                        for p in positions) / len(positions))
                target = torch.tensor(expected, device="cuda")[:, None, None].expand_as(out)
                torch.testing.assert_close(out.float(), target, rtol=0, atol=0.001)
                rows.append({"requests": requests, "lengths": lengths,
                             "observed": out[:, 0, 0].cpu().tolist(),
                             "expected": expected})
            print("FLASHINFER_NUMERIC=" + json.dumps({
                "rank": rank, "dcp_size": dcp_size, "graph": graph,
                "block_size": block_size, "interleave": interleave,
                "rows": rows}), flush=True)


def run_group(graph):
    for block_size in (16, 32):
        for rank in (0, 1):
            check_flashinfer(rank=rank, graph=graph, block_size=block_size)
    check_flashinfer(rank=1, graph=graph, block_size=16, interleave=1)
    check_flashinfer(rank=0, graph=graph, block_size=32, dcp_size=1)


if __name__ == "__main__":
    run_group(False)
    run_group(True)
