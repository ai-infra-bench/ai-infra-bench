#!/usr/bin/env python3
"""Behavioral verifier for production DCP slot mapping.

The verifier enters through production Model Runner initialization, then uses
the existing block-table update and slot-mapping boundaries. It does not name
or call an Oracle-added helper or inspect candidate source.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import torch

sys.path.insert(0, "/workspace/repo")


PAD_SLOT_ID = -1
EXPECTED_CHECKPOINTS = (
    "preflight",
    "slot-1-0-1",
    "slot-2-0-1",
    "slot-2-1-2",
    "slot-4-3-2",
    "graph-replay",
    "graph-block-update",
    "runner-eager-lifecycle",
    "runner-graph-lifecycle",
    "runner-non-dcp-lifecycle",
    "real-backend-eager",
    "real-backend-decode-graph",
    "real-backend-non-dcp",
    "eagle-non-dcp-compatibility",
    "flashinfer-local-eager",
    "flashinfer-local-graph",
    "distributed-flash-attention-generation",
    "distributed-flashinfer-generation",
    "distributed-flash-attention-hnd-generation",
    "distributed-flashinfer-hnd-generation",
    "distributed-flashinfer-chunked-generation",
    "distributed-flashinfer-hnd-chunked-generation",
    "distributed-flash-attention-interleave1-graph",
    "complete",
)


def expected_slots(
    positions: list[int],
    block_ids: list[int],
    block_size: int,
    dcp_size: int,
    dcp_rank: int,
    interleave: int,
) -> list[int]:
    result = []
    virtual_block_size = block_size * dcp_size
    for position in positions:
        virtual_block = position // virtual_block_size
        virtual_offset = position % virtual_block_size
        owner = (virtual_offset // interleave) % dcp_size
        if owner != dcp_rank:
            result.append(PAD_SLOT_ID)
            continue
        local_offset = (
            virtual_offset // (dcp_size * interleave)
        ) * interleave + virtual_offset % interleave
        result.append(block_ids[virtual_block] * block_size + local_offset)
    return result


def configure_group(module, dcp_size: int, dcp_rank: int) -> None:
    import vllm.distributed as distributed
    import vllm.distributed.parallel_state as parallel_state

    group = SimpleNamespace(world_size=dcp_size, rank_in_group=dcp_rank)
    distributed.get_dcp_group = lambda: group
    parallel_state.get_dcp_group = lambda: group
    module.get_dcp_group = lambda: group


def construct_runner(*, dcp_size: int, dcp_rank: int, interleave: int,
                     block_size: int, graph=False, real_backend=False):
    from vllm.config import (
        CacheConfig, CompilationConfig, ModelConfig, ParallelConfig,
        SchedulerConfig, VllmConfig,
    )
    from vllm.config.compilation import CUDAGraphMode
    from vllm.v1.kv_cache_interface import FullAttentionSpec
    from vllm.v1.core.kv_cache_utils import (
        get_kv_cache_groups, get_kv_cache_config_from_groups,
    )
    from vllm.v1.core.kv_cache_manager import KVCacheManager
    import vllm.v1.worker.gpu.block_table as block_table_module
    import vllm.v1.worker.gpu.cudagraph_utils as graph_module
    import vllm.v1.worker.gpu.model_runner as model_runner_module

    configure_group(block_table_module, dcp_size, dcp_rank)
    configure_group(graph_module, dcp_size, dcp_rank)
    configure_group(model_runner_module, dcp_size, dcp_rank)
    with tempfile.TemporaryDirectory(prefix="runner-model-") as model_dir:
        Path(model_dir, "config.json").write_text(json.dumps({
            "model_type": "qwen3", "architectures": ["Qwen3ForCausalLM"],
            "hidden_size": 128, "intermediate_size": 256,
            "num_hidden_layers": 2, "num_attention_heads": 4,
            "num_key_value_heads": 1, "head_dim": 32,
            "vocab_size": 256, "max_position_embeddings": 128,
        }))
        vllm_config = VllmConfig(
            model_config=ModelConfig(
                model=model_dir, dtype="float16", max_model_len=128,
                skip_tokenizer_init=True, enforce_eager=not graph,
            ),
            cache_config=CacheConfig(block_size=block_size, cache_dtype="auto"),
            parallel_config=ParallelConfig(
                tensor_parallel_size=dcp_size,
                distributed_executor_backend="mp",
                decode_context_parallel_size=dcp_size,
                cp_kv_cache_interleave_size=interleave,
            ),
            scheduler_config=SchedulerConfig(
                max_num_batched_tokens=64, max_num_seqs=2,
                max_model_len=128, async_scheduling=False, is_encoder_decoder=False,
            ),
            compilation_config=CompilationConfig(
                mode=0,
                cudagraph_mode=(
                    CUDAGraphMode.FULL_DECODE_ONLY if graph and real_backend
                    else CUDAGraphMode.FULL if graph else CUDAGraphMode.NONE
                ),
                cudagraph_capture_sizes=[1, 2, 4, 8, 16],
            ),
        )
    # Use the ordinary configuration path: two full-attention layers share one
    # group. DCP does not support hybrid groups at this Base. Different block
    # sizes are separate deployments, not an invented multi-group layout.
    layer_specs = {
        (f"model.layers.{index}.self_attn.attn" if real_backend else f"layer{index}"): FullAttentionSpec(
            block_size=block_size, num_kv_heads=1, head_size=32,
            dtype=torch.float16,
        ) for index in range(2)
    }
    groups = get_kv_cache_groups(vllm_config, layer_specs)
    cache_config = get_kv_cache_config_from_groups(
        vllm_config, groups, 4 * 1024 * 1024,
    )
    # Reachability sanity: this exact generated layout is accepted by the
    # scheduler's production coordinator with the real DCP hash granularity.
    KVCacheManager(
        cache_config, max_model_len=128, hash_block_size=block_size * dcp_size,
        enable_caching=True, dcp_world_size=dcp_size,
    )

    class ConsumerBuilder:
        def build(self, *, common_prefix_len, common_attn_metadata):
            return common_attn_metadata

    # Model weights and an attention consumer are deterministic substitutes.
    # Real request state, input buffers, runner and graph manager own all DCP
    # wiring. No candidate-added names/signatures are inspected or supplied.
    if real_backend:
        from vllm.config import set_current_vllm_config
        from vllm.model_executor.layers.attention import Attention
        from vllm.v1.attention.backends.flash_attn import FlashAttentionBackend

        with set_current_vllm_config(vllm_config):
            for layer_name in layer_specs:
                Attention(
                    num_heads=4 // dcp_size, head_size=32, scale=32 ** -0.5,
                    num_kv_heads=1, cache_config=vllm_config.cache_config,
                    prefix=layer_name, attn_backend=FlashAttentionBackend,
                )
            runner = model_runner_module.GPUModelRunner(
                vllm_config, torch.device("cuda")
            )
            runner.initialize_kv_cache(cache_config)
        return runner
    with (
        patch.object(model_runner_module, "init_attn_backend",
                     return_value=({}, [ConsumerBuilder() for _ in groups])),
        patch.object(model_runner_module, "init_kv_cache", return_value={}),
    ):
        runner = model_runner_module.GPUModelRunner(
            vllm_config, torch.device("cuda")
        )
        runner.initialize_kv_cache(cache_config)
    return runner


def construct_tables(module, *, dcp_size: int, dcp_rank: int, interleave: int,
                     block_size: int):
    return construct_runner(
        dcp_size=dcp_size, dcp_rank=dcp_rank, interleave=interleave,
        block_size=block_size,
    ).block_tables


def populate(tables, *, block_size: int, dcp_size: int):
    per_request = []
    for req_index, base in enumerate((10, 40)):
        groups = []
        for group_index in range(1):
            width = (128 + block_size * dcp_size - 1) // (block_size * dcp_size)
            groups.append([base + group_index * 20 + i for i in range(width)])
        tables.append_block_ids(req_index, tuple(groups), overwrite=True)
        per_request.append(groups)
    tables.apply_staged_writes()
    return per_request


def run_case(module, *, dcp_size: int, dcp_rank: int, interleave: int,
             block_size: int) -> None:
    tables = construct_tables(
        module, dcp_size=dcp_size, dcp_rank=dcp_rank, interleave=interleave,
        block_size=block_size,
    )
    block_ids = populate(tables, block_size=block_size, dcp_size=dcp_size)
    # Include both early decode positions and positions close to max_model_len.
    # This exercises capacity without prescribing an internal table width: a
    # compact table and a safely over-allocated table are both valid.
    positions = list(range(54, 64)) + list(range(122, 128))
    split = 10
    slots = tables.compute_slot_mappings(
        torch.tensor([0, 1], dtype=torch.int32, device="cuda"),
        torch.tensor([0, split, len(positions)], dtype=torch.int32, device="cuda"),
        torch.tensor(positions, dtype=torch.int64, device="cuda"),
    )
    torch.cuda.synchronize()
    for group_index in range(1):
        expected = expected_slots(
            positions[:split],
            block_ids[0][group_index],
            block_size,
            dcp_size,
            dcp_rank,
            interleave,
        ) + expected_slots(
            positions[split:],
            block_ids[1][group_index],
            block_size,
            dcp_size,
            dcp_rank,
            interleave,
        )
        actual = slots[group_index].cpu().tolist()
        if actual != expected:
            raise AssertionError(
                f"slot mismatch size={dcp_size} rank={dcp_rank} "
                f"interleave={interleave} group={group_index}: "
                f"expected={expected} actual={actual}"
            )


def check_graph_replay(module, *, block_size: int) -> None:
    dcp_size, dcp_rank, interleave = 2, 1, 2
    tables = construct_tables(
        module, dcp_size=dcp_size, dcp_rank=dcp_rank, interleave=interleave,
        block_size=block_size,
    )
    block_ids = populate(tables, block_size=block_size, dcp_size=dcp_size)
    idx = torch.tensor([0, 1], dtype=torch.int32, device="cuda")
    starts = torch.tensor([0, 8, 16], dtype=torch.int32, device="cuda")
    positions = torch.tensor(
        list(range(24, 32)) + list(range(56, 64)),
        dtype=torch.int64, device="cuda",
    )
    tables.compute_slot_mappings(idx, starts, positions)
    torch.cuda.synchronize()

    graph = torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
        slots = tables.compute_slot_mappings(idx, starts, positions)

    # A later decode step can compact/reorder requests and change their token
    # counts while replaying the same captured graph.  Mutate all three graph
    # inputs in place so a candidate cannot pass by capturing only positions.
    heldout = list(range(31, 36)) + list(range(61, 72))
    idx.copy_(torch.tensor([1, 0], dtype=torch.int32, device="cuda"))
    starts.copy_(torch.tensor([0, 5, 16], dtype=torch.int32, device="cuda"))
    positions.copy_(torch.tensor(heldout, dtype=torch.int64, device="cuda"))
    graph.replay()
    torch.cuda.synchronize()
    for group_index in range(1):
        expected = expected_slots(
            heldout[:5],
            block_ids[1][group_index],
            block_size,
            dcp_size,
            dcp_rank,
            interleave,
        ) + expected_slots(
            heldout[5:],
            block_ids[0][group_index],
            block_size,
            dcp_size,
            dcp_rank,
            interleave,
        )
        actual = slots[group_index].cpu().tolist()
        if actual != expected:
            raise AssertionError(
                "CUDA graph replay used stale or incorrect inputs: "
                f"group={group_index} {actual}!={expected}"
            )

    # KV blocks can be recycled between decode steps without recapturing the
    # graph. Change the actual staged block-table backing storage, not a mock
    # of the slot-mapping implementation, for this supported cache layout.
    replacement_groups = []
    for group_index in range(1):
        width = (128 + block_size * dcp_size - 1) // (block_size * dcp_size)
        replacement = [120 + group_index * 40 + i for i in range(width)]
        replacement_groups.append(replacement)
    tables.append_block_ids(1, tuple(replacement_groups), overwrite=True)
    block_ids[1] = replacement_groups
    tables.apply_staged_writes()
    graph.replay()
    torch.cuda.synchronize()
    for group_index in range(1):
        expected = expected_slots(
            heldout[:5], block_ids[1][group_index], block_size,
            dcp_size, dcp_rank, interleave,
        ) + expected_slots(
            heldout[5:], block_ids[0][group_index], block_size,
            dcp_size, dcp_rank, interleave,
        )
        actual = slots[group_index].cpu().tolist()
        if actual != expected:
            raise AssertionError(
                "CUDA graph replay used stale KV block IDs: "
                f"group={group_index} {actual}!={expected}"
            )


def check_runner_lifecycle(*, dcp_size: int, dcp_rank: int, graph: bool,
                           block_size: int, real_backend=False) -> None:
    """Scheduler messages -> real runner/graphs/sampler -> per-request tokens.

    The synthetic consumer tests token/position/slot association and lifecycle,
    not a prescribed intermediate representation of rank-local lengths. Real
    attention cases and full-engine generation check that length conversion is
    performed somewhere in the actual execution path. We substitute model
    arithmetic, not runner preparation or graph wiring.
    """
    from vllm.forward_context import get_forward_context
    from vllm.sampling_params import SamplingParams
    from vllm.v1.core.sched.output import NewRequestData, SchedulerOutput
    import vllm.v1.worker.gpu.cudagraph_utils as graph_module

    if real_backend:
        from vllm.v1.attention.backends.fa_utils import get_flash_attn_version

    interleave = 2
    runner = construct_runner(
        dcp_size=dcp_size, dcp_rank=dcp_rank, interleave=interleave,
        block_size=block_size, graph=graph, real_backend=real_backend,
    )

    class MetadataConsumer(torch.nn.Module):
        def __init__(self):
            super().__init__()
            if real_backend:
                self.keys = torch.zeros((256, block_size, 1, 32),
                                        dtype=torch.float16, device="cuda")
                slots = torch.arange(256 * block_size, device="cuda")
                self.values = (slots.remainder(127).float() / 128).to(torch.float16)
                self.values = self.values.view(256, block_size, 1, 1).expand(-1, -1, 1, 32).contiguous()

        def forward(self, input_ids, positions, **kwargs):
            context = get_forward_context()
            names = ([f"model.layers.{i}.self_attn.attn" for i in range(2)]
                     if real_backend else ["layer0", "layer1"])
            common = context.attn_metadata[names[0]]
            fingerprint = (
                input_ids.to(torch.int64) + 3 * positions
                + 5 * context.slot_mapping[names[0]]
                + 12 * context.slot_mapping[names[1]]
            )
            if real_backend:
                # Observe the actual backend's consumed lengths; do not require
                # the runner to populate an optional CommonAttentionMetadata
                # field which these real backends need not consume.
                lengths = (common.dcp_context_kv_lens if dcp_size > 1
                           else common.seq_lens)
                rows = torch.bucketize(
                    torch.arange(input_ids.shape[0], device=input_ids.device),
                    common.query_start_loc[1:], right=True,
                ).clamp(max=lengths.shape[0] - 1)
                fingerprint = fingerprint + 7 * lengths[rows]
            fingerprint = fingerprint.remainder(256).unsqueeze(1).float()
            if not real_backend:
                return fingerprint
            # Real paged-attention CUDA math consumes real backend metadata.
            # Uniform attention over a deterministic cache has an independent
            # arithmetic reference; no model weights or cross-rank collective
            # are needed for this local-rank context-consumption boundary.
            from vllm.v1.attention.backends.fa_utils import (
                flash_attn_varlen_func, get_flash_attn_version,
            )
            fa_version = get_flash_attn_version()
            query = torch.zeros((input_ids.shape[0], 4 // dcp_size, 32),
                                dtype=torch.float16, device=input_ids.device)
            if fa_version == 2 and dcp_size > 1 and common.max_query_len > 1:
                # FA2 paged-varlen does not accept a batch that mixes rows
                # with and without context. This component check validates the
                # runner's real page tables and lengths one request at a time;
                # the full-engine checks below exercise production batching.
                attended = torch.zeros_like(query)
                query_starts = common.query_start_loc.cpu().tolist()
                for req_index, (start, end) in enumerate(
                    zip(query_starts, query_starts[1:])
                ):
                    local_length = int(lengths[req_index].item())
                    if local_length == 0:
                        continue
                    single_query_start = torch.tensor(
                        [0, end - start], dtype=torch.int32,
                        device=input_ids.device,
                    )
                    flash_attn_varlen_func(
                        q=query[start:end], k=self.keys, v=self.values,
                        out=attended[start:end],
                        cu_seqlens_q=single_query_start,
                        max_seqlen_q=end - start,
                        seqused_k=lengths[req_index:req_index + 1],
                        max_seqlen_k=local_length,
                        softmax_scale=32 ** -0.5, causal=False,
                        block_table=common.block_table[req_index:req_index + 1],
                        fa_version=fa_version, num_splits=1,
                    )
            else:
                attended = flash_attn_varlen_func(
                    q=query, k=self.keys, v=self.values,
                    cu_seqlens_q=common.query_start_loc,
                    max_seqlen_q=common.max_query_len, seqused_k=lengths,
                    max_seqlen_k=(common.max_dcp_context_kv_len if dcp_size > 1
                                  else common.max_seq_len),
                    softmax_scale=32 ** -0.5, causal=False,
                    block_table=common.block_table,
                    fa_version=fa_version, num_splits=1,
                )
            return torch.cat((fingerprint, attended.float().mean(dim=(1, 2)).unsqueeze(1)), dim=1)

        def compute_logits(self, hidden_states):
            if real_backend:
                self.observed_attention = hidden_states[:, 1].detach().clone()
            logits = torch.full(
                (hidden_states.shape[0], 256), -100.0,
                device=hidden_states.device,
            )
            return logits.scatter_(1, hidden_states[:, :1].long(), 100.0)

    runner.model = MetadataConsumer().cuda()

    @contextmanager
    def local_capture_stream(device):
        # No model collective is used by this local-rank consumer. Preserve the
        # real CUDA capture stream while omitting distributed communicator setup.
        stream = torch.cuda.Stream(device=device)
        stream.wait_stream(torch.cuda.current_stream(device))
        with torch.cuda.stream(stream):
            yield
        torch.cuda.current_stream(device).wait_stream(stream)

    if graph:
        with (
            patch.object(graph_module, "graph_capture", local_capture_stream),
            patch.object(graph_module, "is_global_first_rank", return_value=False),
        ):
            runner.capture_model()

    boundary = block_size * dcp_size
    long_length = min(boundary - 1, 63)
    short_length = 64 - long_length
    prompts = {
        "long-a": list(range(10, 10 + short_length)),
        "long-b": list(range(50, 50 + long_length)),
        "new-c": [91, 92, 93],
        "reuse-d": [107, 108],
    }
    bases = {"long-a": 10, "long-b": 60, "new-c": 110, "reuse-d": 160}
    state = {}
    sampling = SamplingParams(temperature=0, max_tokens=16, ignore_eos=True)
    plans = [
        ({"long-a": short_length, "long-b": long_length}, set()),
        ({"long-b": 1, "long-a": 1}, set()),
        ({"long-b": 1, "new-c": 3}, {"long-a"}),
        ({"new-c": 1, "long-b": 1}, set()),
        ({"long-b": 1}, {"new-c"}),
        ({"reuse-d": 2}, {"long-b"}),
        ({"reuse-d": 1}, set()),
        ({}, {"reuse-d"}),
    ]
    for step, (counts, finished) in enumerate(plans):
        output = SchedulerOutput.make_empty()
        output.finished_req_ids = finished
        output.num_scheduled_tokens = counts
        output.total_num_scheduled_tokens = sum(counts.values())
        expected = {}
        expected_attention = {}
        for req_id, count in counts.items():
            new = req_id not in state
            if new:
                state[req_id] = {
                    "tokens": prompts[req_id].copy(), "computed": 0,
                    "blocks": [[]],
                }
            record = state[req_id]
            end = record["computed"] + count
            additions = []
            for group, size in enumerate((block_size,)):
                needed = (end + size * dcp_size - 1) // (size * dcp_size)
                blocks = record["blocks"][group]
                added = [
                    bases[req_id] + group * 20 + i
                    for i in range(len(blocks), needed)
                ]
                blocks.extend(added)
                additions.append(added)
            if new:
                output.scheduled_new_reqs.append(NewRequestData(
                    req_id=req_id, prompt_token_ids=prompts[req_id].copy(),
                    prefill_token_ids=prompts[req_id].copy(), mm_features=[],
                    sampling_params=sampling, pooling_params=None,
                    block_ids=tuple(record["blocks"]), num_computed_tokens=0,
                    lora_request=None,
                ))
            else:
                cached = output.scheduled_cached_reqs
                cached.req_ids.append(req_id)
                cached.new_token_ids.append([])
                cached.new_block_ids.append(
                    tuple(additions) if any(additions) else None
                )
                cached.num_computed_tokens.append(record["computed"])
                cached.num_output_tokens.append(
                    len(record["tokens"]) - len(prompts[req_id])
                )
            position = end - 1
            slots = [
                expected_slots(
                    [position], record["blocks"][group], size,
                    dcp_size, dcp_rank, interleave,
                )[0]
                for group, size in enumerate((block_size,))
            ]
            context_end = end - count if real_backend and dcp_size > 1 else end
            local_length = sum(
                (p // interleave) % dcp_size == dcp_rank for p in range(context_end)
            )
            expected[req_id] = (
                record["tokens"][position] + 3 * position
                + 5 * slots[0] + 12 * slots[0]
                + (7 * local_length if real_backend else 0)
            ) % 256
            if real_backend:
                expected_attention[req_id] = (
                    sum(((record["blocks"][0][p // block_size] * block_size
                          + p % block_size) % 127) / 128 for p in range(local_length))
                    / local_length if local_length else 0.0
                )
        if real_backend:
            print("REAL_BACKEND_STEP=" + json.dumps({
                "fa_version": get_flash_attn_version(),
                "block_size": block_size,
                "dcp_size": dcp_size,
                "dcp_rank": dcp_rank,
                "graph": graph,
                "step": step,
                "requests": list(counts),
            }), flush=True)
        runner.execute_model(output)
        if real_backend:
            # Surface asynchronous kernel failures at the operation that
            # launched them instead of during a later sampler copy.
            torch.cuda.synchronize()
        if not counts:
            continue
        sampled = runner.sample_tokens(None)
        if hasattr(sampled, "get_output"):
            sampled = sampled.get_output()
        observed = dict(zip(sampled.req_ids, sampled.sampled_token_ids))
        wanted = {req_id: [token] for req_id, token in expected.items()}
        if real_backend:
            observed_attention = runner.model.observed_attention.cpu().tolist()
            for req_id, actual in zip(sampled.req_ids, observed_attention):
                target = expected_attention[req_id]
                if not abs(actual - target) < 0.002:
                    raise AssertionError(
                        f"real paged-attention mismatch step={step} request={req_id} "
                        f"DCP={dcp_size}/{dcp_rank} graph={graph}: {actual} != {target}"
                    )
        if observed != wanted:
            raise AssertionError(
                f"runner lifecycle step={step} graph={graph} DCP={dcp_size}/"
                f"{dcp_rank}: expected={wanted} actual={observed}"
            )
        for req_id, count in counts.items():
            state[req_id]["computed"] += count
            state[req_id]["tokens"].append(expected[req_id])


def run_suite(emit) -> None:
    import vllm
    import vllm.v1.worker.gpu.block_table as block_table_module

    repo = Path("/workspace/repo").resolve()
    source = Path(vllm.__file__).resolve()
    if repo not in source.parents:
        raise AssertionError(f"candidate source is not active: {source}")
    if not torch.cuda.is_available():
        raise AssertionError("CUDA is required")
    emit("preflight", True)

    for case in ((1, 0, 1), (2, 0, 1), (2, 1, 2), (4, 3, 2)):
        for block_size in (16, 32):
            run_case(
                block_table_module,
                dcp_size=case[0], dcp_rank=case[1], interleave=case[2],
                block_size=block_size,
            )
        emit(f"slot-{case[0]}-{case[1]}-{case[2]}", True)
    for block_size in (16, 32):
        check_graph_replay(block_table_module, block_size=block_size)
    emit("graph-replay", True)
    emit("graph-block-update", True)
    for block_size in (16, 32):
        check_runner_lifecycle(dcp_size=2, dcp_rank=1, graph=False,
                               block_size=block_size)
    emit("runner-eager-lifecycle", True)
    for block_size in (16, 32):
        check_runner_lifecycle(dcp_size=2, dcp_rank=1, graph=True,
                               block_size=block_size)
    emit("runner-graph-lifecycle", True)
    for block_size in (16, 32):
        check_runner_lifecycle(dcp_size=1, dcp_rank=0, graph=True,
                               block_size=block_size)
    emit("runner-non-dcp-lifecycle", True)
    for block_size in (16, 32):
        for rank in (0, 1):
            check_runner_lifecycle(dcp_size=2, dcp_rank=rank, graph=False,
                                   block_size=block_size, real_backend=True)
    emit("real-backend-eager", True)
    for block_size in (16, 32):
        for rank in (0, 1):
            check_runner_lifecycle(dcp_size=2, dcp_rank=rank, graph=True,
                                   block_size=block_size, real_backend=True)
    emit("real-backend-decode-graph", True)
    for block_size in (16, 32):
        for graph in (False, True):
            check_runner_lifecycle(dcp_size=1, dcp_rank=0, graph=graph,
                                   block_size=block_size, real_backend=True)
    emit("real-backend-non-dcp", True)
    import importlib.util
    eagle_spec = importlib.util.spec_from_file_location(
        "eagle_compatibility", Path(__file__).with_name("verify_eagle_nondcp.py")
    )
    eagle_check = importlib.util.module_from_spec(eagle_spec)
    eagle_spec.loader.exec_module(eagle_check)
    eagle_check.check_eagle_nondcp()
    emit("eagle-non-dcp-compatibility", True)
    fi_spec = importlib.util.spec_from_file_location(
        "flashinfer_compatibility", Path(__file__).with_name("verify_flashinfer_dcp.py")
    )
    fi_check = importlib.util.module_from_spec(fi_spec)
    fi_spec.loader.exec_module(fi_check)
    fi_check.run_group(False)
    emit("flashinfer-local-eager", True)
    fi_check.run_group(True)
    emit("flashinfer-local-graph", True)
    distributed_spec = importlib.util.spec_from_file_location(
        "distributed_generation", Path(__file__).with_name("verify_distributed_generation.py")
    )
    distributed_check = importlib.util.module_from_spec(distributed_spec)
    distributed_spec.loader.exec_module(distributed_check)
    distributed_check.run_group("FLASH_ATTN", "NHD")
    emit("distributed-flash-attention-generation", True)
    distributed_check.run_group("FLASHINFER", "NHD")
    emit("distributed-flashinfer-generation", True)
    distributed_check.run_group("FLASH_ATTN", "HND")
    emit("distributed-flash-attention-hnd-generation", True)
    distributed_check.run_group("FLASHINFER", "HND")
    emit("distributed-flashinfer-hnd-generation", True)
    distributed_check.run_group("FLASHINFER", "NHD", "chunked")
    emit("distributed-flashinfer-chunked-generation", True)
    distributed_check.run_group("FLASHINFER", "HND", "chunked")
    emit("distributed-flashinfer-hnd-chunked-generation", True)
    for layout in ("NHD", "HND"):
        distributed_check.check("FLASH_ATTN", True, layout, "interleave1")
    emit("distributed-flash-attention-interleave1-graph", True)
    print(
        "PASS: production slot mapping handles non-DCP, held-out DCP ranks, "
        "interleaving, supported block sizes, requests, CUDA graph replay, "
        "and graph attention metadata"
    )
    print(f"candidate_source={source} gpu={torch.cuda.get_device_name(0)}")
    emit("complete", True)


if __name__ == "__main__":
    run_suite(lambda name, value: print(f"checkpoint={name} value={value}"))
