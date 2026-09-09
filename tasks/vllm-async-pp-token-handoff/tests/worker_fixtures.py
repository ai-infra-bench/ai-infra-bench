"""Real runner initialization with deterministic model-output inputs.

The production constructor, buffers, InputBatch, bookkeeping and next-input
preparation execute unchanged. Model weights and attention computation are not
needed to exercise sampled-token transport. No candidate-private attributes are
invented by this fixture.
"""
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

from vllm.config import CacheConfig, ModelConfig, ParallelConfig, SchedulerConfig, VllmConfig, set_current_vllm_config
from vllm.sampling_params import SamplingParams
from vllm.v1.kv_cache_interface import KVCacheConfig
from vllm.v1.worker.gpu_input_batch import CachedRequestState
from vllm.v1.worker.gpu_model_runner import GPUModelRunner


def initialize_runner_groups(rank, world_size):
    """Initialize production world/TP/PP groups on the existing NCCL world."""
    from vllm.distributed.parallel_state import (
        get_pp_group, init_distributed_environment, initialize_model_parallel,
    )
    init_distributed_environment(
        world_size=world_size, rank=rank, distributed_init_method="env://",
        local_rank=int(os.environ["LOCAL_RANK"]), backend="nccl",
    )
    initialize_model_parallel(tensor_model_parallel_size=1,
                              pipeline_model_parallel_size=world_size, backend="nccl")
    return get_pp_group()


def make_runner(req_ids, discard_mask, prior_outputs, sampled=None):
    device = torch.device("cuda", int(os.environ.get("LOCAL_RANK", "0")))
    model_config = ModelConfig(
        model=str(Path(__file__).parent / "fixtures/opt-125m"),
        dtype="float16", seed=42, max_model_len=64,
        skip_tokenizer_init=True, enforce_eager=True,
    )
    config = VllmConfig(
        model_config=model_config,
        cache_config=CacheConfig(block_size=16, swap_space=0,
                                 enable_prefix_caching=False),
        scheduler_config=SchedulerConfig(
            max_num_seqs=16, max_num_batched_tokens=64, max_model_len=64,
            is_encoder_decoder=False, async_scheduling=True,
        ),
        parallel_config=ParallelConfig(pipeline_parallel_size=2,
                                       distributed_executor_backend="mp"),
    )
    with set_current_vllm_config(config):
        runner = GPUModelRunner(config, device)
    # No attention is executed. This is the post-cache-setup input to the
    # sampled-token lifecycle; keep the constructor's real InputBatch/buffers.
    runner.kv_cache_config = KVCacheConfig(
        num_blocks=1, kv_cache_tensors=[], kv_cache_groups=[])
    runner.input_ids.cpu.fill_(17)
    runner.discard_request_mask.np[:len(req_ids)] = discard_mask
    runner.discard_request_mask.copy_to_gpu(len(req_ids))
    for req_id in req_ids:
        request = CachedRequestState(
            req_id=req_id, prompt_token_ids=list(range(8)), mm_features=[],
            sampling_params=SamplingParams(temperature=0, max_tokens=16),
            generator=None, block_ids=([0],), num_computed_tokens=8,
            output_token_ids=list(prior_outputs[req_id]),
        )
        runner.requests[req_id] = request
        runner.input_batch.add_request(request)
    runner.input_batch.refresh_metadata()
    if sampled is not None:
        scheduler_output = SimpleNamespace(
            total_num_scheduled_tokens=len(req_ids),
            num_scheduled_tokens={req_id: 1 for req_id in req_ids},
        )
        runner.execute_model_state = (
            scheduler_output, torch.empty(1, device=device), None, None,
            torch.empty((len(req_ids), 1), device=device),
            None, None, None, None, None,
        )
        runner._sample = lambda logits, metadata: SimpleNamespace(
            sampled_token_ids=sampled, logprobs_tensors=None)
    return runner


def next_inputs(runner, req_ids, *, scheduler_output=None):
    """Complete cached-state update, then consume received tokens on the GPU.

    req_ids gives the next consumer order. If a real scheduler output is supplied
    it crosses this boundary directly; otherwise a valid one-token decode event
    is constructed for the retained requests.
    """
    if scheduler_output is None:
        scheduler_output = SimpleNamespace(
            finished_req_ids=set(runner.requests) - set(req_ids),
            free_encoder_mm_hashes=[], scheduled_new_reqs=[],
            num_scheduled_tokens={req_id: 1 for req_id in req_ids},
            total_num_scheduled_tokens=len(req_ids),
            scheduled_spec_decode_tokens={},
            scheduled_cached_reqs=SimpleNamespace(
                req_ids=list(req_ids), resumed_req_ids=set(),
                num_computed_tokens=[runner.requests[r].num_tokens - 1
                                     for r in req_ids],
                new_block_ids=[None] * len(req_ids), new_token_ids=[],
                num_output_tokens=[len(runner.requests[r].output_token_ids)
                                   for r in req_ids],
            ),
        )
    GPUModelRunner._update_states(runner, scheduler_output)
    for target, req_id in enumerate(req_ids):
        current = runner.input_batch.req_id_to_index[req_id]
        if current != target:
            runner.input_batch.swap_states(target, current)
    runner.input_batch.refresh_metadata()
    counts = [scheduler_output.num_scheduled_tokens[r] for r in req_ids]
    cumulative = np.cumsum(counts, dtype=np.int32)
    GPUModelRunner._prepare_input_ids(
        runner, scheduler_output, sum(counts), cumulative)
    # CPU inspection belongs to the test consumer, after GPU input preparation.
    return runner.input_ids.gpu[:sum(counts)].cpu().tolist()
