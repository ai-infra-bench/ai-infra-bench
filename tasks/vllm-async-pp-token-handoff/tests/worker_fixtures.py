"""Real scheduler-to-runner transitions with deterministic model arithmetic.

Requests enter through add_request; every execution consumes the complete object
returned by the candidate scheduler. No scheduler output or cached request state
is reconstructed by the verifier.
"""
import os
from pathlib import Path
from weakref import WeakKeyDictionary
from contextlib import nullcontext

import torch
import torch.distributed as dist

from vllm.config import CacheConfig, ModelConfig, ParallelConfig, SchedulerConfig, VllmConfig, set_current_vllm_config
from vllm.sampling_params import SamplingParams
from vllm.v1.kv_cache_interface import KVCacheConfig
from vllm.v1.request import Request
from vllm.v1.worker.gpu_model_runner import GPUModelRunner
from task_fixtures import build_scheduler

PRIOR_INPUT_EVENTS = WeakKeyDictionary()
MODEL_INPUTS = WeakKeyDictionary()
WORKLOADS = WeakKeyDictionary()


def initialize_runner_groups(rank, world_size):
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


class RunnerWorkload:
    """Own test inputs and the real scheduler; never populate runner internals."""

    def __init__(self, req_ids, discard_mask, sampled, *, prompts=None,
                 chunk_size=8, async_mode=True, budgets=None):
        from vllm.sequence import IntermediateTensors
        from vllm.distributed.parallel_state import get_pp_group
        device = torch.device("cuda", int(os.environ.get("LOCAL_RANK", "0")))
        model = str(Path(__file__).parent / "fixtures/opt-125m")
        self.prompts = prompts or {
            r: list(range(11, 11 + chunk_size * (3 if discard_mask[i] else 1)))
            for i, r in enumerate(req_ids)
        }
        self.positions = dict.fromkeys(req_ids, 0)
        self.sampled = sampled
        self.sample_ids = list(req_ids)
        self.config = VllmConfig(
            model_config=ModelConfig(model=model, dtype="float16", seed=42,
                max_model_len=64, skip_tokenizer_init=True, enforce_eager=True),
            cache_config=CacheConfig(block_size=16, swap_space=0,
                                     enable_prefix_caching=False),
            scheduler_config=SchedulerConfig(max_num_seqs=16,
                max_num_batched_tokens=64, max_model_len=64,
                is_encoder_decoder=False, async_scheduling=async_mode,
                long_prefill_token_threshold=chunk_size),
            parallel_config=ParallelConfig(pipeline_parallel_size=2,
                                           distributed_executor_backend="mp"),
        )
        self.scheduler = build_scheduler(model, async_scheduling=async_mode,
            pipeline_parallel_size=2, max_model_len=64,
            max_num_seqs=16, max_num_batched_tokens=64,
            long_prefill_token_threshold=chunk_size)
        for req_id in req_ids:
            self.scheduler.add_request(Request(request_id=req_id,
                prompt_token_ids=self.prompts[req_id],
                sampling_params=SamplingParams(temperature=0,
                    max_tokens=(budgets or {}).get(req_id, 16), ignore_eos=True),
                pooling_params=None, eos_token_id=None))
        with set_current_vllm_config(self.config):
            self.runner = GPUModelRunner(self.config, device)
        runner = self.runner
        # FixedModel has no attention. Real scheduler KV allocation and the
        # runner's normal new/cached request handling still initialize the batch.
        runner.kv_cache_config = KVCacheConfig(
            num_blocks=4096, kv_cache_tensors=[], kv_cache_groups=[])
        workload = self

        class FixedModel(torch.nn.Module):
            def forward(self, input_ids, positions, intermediate_tensors, inputs_embeds):
                MODEL_INPUTS[runner] = (input_ids.clone(), tuple(runner.input_batch.req_ids))
                hidden = torch.zeros((len(positions), 1), device=device)
                if not get_pp_group().is_last_rank:
                    return IntermediateTensors({"hidden_states": hidden})
                return hidden

            def compute_logits(self, hidden):
                logits = torch.full((len(hidden), 1024), -100.0, device=device)
                if workload.sampled is not None:
                    rows = [workload.sample_ids.index(r)
                            for r in runner.input_batch.req_ids[:len(hidden)]]
                    selected = workload.sampled.index_select(
                        0, torch.tensor(rows, device=device))
                    logits.scatter_(1, selected.to(dtype=torch.int64), 100.0)
                return logits

        runner.model = FixedModel()
        runner.intermediate_tensors = IntermediateTensors({
            "hidden_states": torch.zeros((64, 1), device=device),
        })
        WORKLOADS[runner] = self

    def execute_next(self, *, observer=None):
        self.step = self.scheduler.schedule()
        for req_id, count in self.step.num_scheduled_tokens.items():
            self.positions[req_id] += count
        with set_current_vllm_config(self.config):
            with observer.observe() if observer is not None else nullcontext():
                result = self.runner.execute_model(
                    self.step, self.runner.intermediate_tensors)
        return result

    def collect(self, output):
        """Collect the real last-stage output outside the observed handoff.

        Feed it to both scheduler replicas, preserving candidate-added metadata.
        The replicas stand in for the engine's single scheduler in this component
        test. No current output is collected before the async next-input check.
        """
        from vllm.distributed.parallel_state import get_pp_group
        if get_pp_group().is_last_rank:
            output = output.get_output() if hasattr(output, "get_output") else output
        else:
            output = None
        payload = [output]
        dist.broadcast_object_list(payload, src=1, group=get_pp_group().cpu_group)
        return self.scheduler.update_from_output(self.step, payload[0])

    def mark_prior_input_events(self):
        PRIOR_INPUT_EVENTS[self.runner] = {
            id(value) for value in vars(self.runner).values()
            if isinstance(value, (torch.Event, torch.cuda.Event)) and value.device is not None
        }


def make_runner(req_ids, discard_mask, sampled=None, *, prompts=None,
                chunk_size=8, async_mode=True, budgets=None, warmup_rounds=0):
    workload = RunnerWorkload(req_ids, discard_mask, sampled, prompts=prompts,
        chunk_size=chunk_size, async_mode=async_mode, budgets=budgets)
    runner = workload.runner
    # Fully execute and collect warmup to create generated history, without
    # manufacturing cached tokens or assuming a placeholder representation.
    for round_index in range(warmup_rounds):
        workload.sampled = torch.tensor(
            [[31 + i + round_index] for i in range(len(req_ids))],
            dtype=torch.int32, device=runner.device)
        workload.execute_next()
        workload.collect(runner.sample_tokens(None))
    workload.sampled = sampled
    workload.execute_next()
    workload.mark_prior_input_events()
    return runner


def next_inputs(runner, req_ids, *, inspect_cpu=True, observer=None):
    workload = WORKLOADS[runner]
    # Exercise a valid batch row change without reconstructing the scheduler
    # message. All metadata comes from the candidate's real schedule() result.
    for target, req_id in enumerate(req_ids):
        current = runner.input_batch.req_id_to_index[req_id]
        if current != target:
            runner.input_batch.swap_states(target, current)
    workload.execute_next(observer=observer)
    inputs = model_inputs_in_request_order(runner, workload.step, req_ids)
    return inputs.cpu().tolist() if inspect_cpu else inputs


def model_inputs_in_request_order(runner, step, req_ids):
    offsets = {}
    offset = 0
    input_ids, row_order = MODEL_INPUTS[runner]
    for req_id in row_order:
        count = step.num_scheduled_tokens[req_id]
        offsets[req_id] = list(range(offset, offset + count))
        offset += count
    indices = [i for req_id in req_ids for i in offsets[req_id]]
    index = torch.tensor(indices, dtype=torch.int64, device=input_ids.device)
    return input_ids.index_select(0, index)


def output_tokens_by_request(output):
    assert len(output.req_ids) == len(output.sampled_token_ids)
    assert len(set(output.req_ids)) == len(output.req_ids)
    return dict(zip(output.req_ids, output.sampled_token_ids))
