#!/usr/bin/env python3
"""Behavior-only streaming-session continuation contract."""

import json
import os
import random
import string
import sys
import traceback
from types import SimpleNamespace

import torch
from workload import load_workload

sys.path.insert(0, "/workspace/repo")

from vllm.sampling_params import SamplingParams
from vllm.v1.core.sched.output import CachedRequestData, NewRequestData
from vllm.v1.worker.gpu_input_batch import CachedRequestState, InputBatch
from vllm.pooling_params import PoolingParams
import vllm.v1.worker.gpu_model_runner as runner_module
from vllm.v1.worker.gpu_model_runner import GPUModelRunner



def cached(req_id, prompt, outputs, *, marker=None):
    state = CachedRequestState(
        req_id=req_id,
        prompt_token_ids=list(prompt),
        mm_features=[] if marker is None else [marker],
        sampling_params=SamplingParams(temperature=0.0, max_tokens=8),
        generator=None,
        block_ids=([4],),
        num_computed_tokens=len(prompt),
        output_token_ids=list(outputs),
    )
    return state


def continuation(
    req_id,
    prompt,
    *,
    marker,
    temperature,
    blocks,
    computed,
    prompt_embeds=None,
    pooling_params=None,
):
    return NewRequestData(
        req_id=req_id,
        prompt_token_ids=None if prompt is None else list(prompt),
        prompt_embeds=prompt_embeds,
        mm_features=[marker],
        sampling_params=SamplingParams(temperature=temperature, max_tokens=50),
        pooling_params=pooling_params,
        block_ids=blocks,
        num_computed_tokens=computed,
        lora_request=None,
    )


def scheduler_output(records, scheduled_ids, finished_ids=None):
    cached_data = CachedRequestData(
        req_ids=[],
        resumed_req_ids=set(),
        new_token_ids=[],
        all_token_ids={},
        new_block_ids=[],
        num_computed_tokens=[],
        num_output_tokens=[],
    )
    return SimpleNamespace(
        finished_req_ids=set() if finished_ids is None else set(finished_ids),
        free_encoder_mm_hashes=[],
        num_scheduled_tokens={req_id: 1 for req_id in scheduled_ids},
        scheduled_cached_reqs=cached_data,
        scheduled_new_reqs=list(records),
        scheduled_spec_decode_tokens={},
    )


def make_runner(states):
    runner = object.__new__(GPUModelRunner)
    runner.requests = dict(states)
    runner.num_prompt_logprobs = {}
    runner.encoder_cache = {}
    runner.input_batch = InputBatch(
        max_num_reqs=8, max_model_len=128, max_num_batched_tokens=128,
        device=torch.device("cpu"), pin_memory=False, vocab_size=32000,
        block_sizes=[16], kernel_block_sizes=[16],
    )
    for state in states.values():
        runner.input_batch.add_request(state)
    runner.input_batch.refresh_metadata()
    runner.is_pooling_model = False
    runner.device = "cpu"
    runner.uses_mrope = False
    runner.uses_xdrope_dim = 0
    runner.use_async_scheduling = False
    runner._get_valid_sampled_token_count = lambda: None
    runner._may_reorder_batch = lambda output: None
    return runner


def apply_update(runner, records, scheduled_ids=None, finished_ids=None):
    previous = runner_module.get_pp_group
    runner_module.get_pp_group = lambda: SimpleNamespace(is_last_rank=True)
    try:
        if scheduled_ids is None:
            scheduled_ids = set(runner.requests) | {record.req_id for record in records}
        GPUModelRunner._update_states(
            runner,
            scheduler_output(records, scheduled_ids, finished_ids),
        )
    finally:
        runner_module.get_pp_group = previous


def random_id(rng, prefix):
    return prefix + "-" + "".join(rng.choice(string.ascii_lowercase) for _ in range(12))


def snapshot(runner):
    batch = runner.input_batch
    states = {}
    for rid, state in runner.requests.items():
        i = batch.req_id_to_index[rid]
        n = state.num_prompt_tokens
        states[rid] = {
            "prompt": state.prompt_token_ids,
            "embeds": None if state.prompt_embeds is None else state.prompt_embeds.tolist(),
            "outputs": list(state.output_token_ids), "length": n,
            "computed": state.num_computed_tokens, "blocks": state.block_ids,
            "mm": state.mm_features,
            "temperature": state.sampling_params.temperature,
            "seed": state.sampling_params.seed,
            "generator_seed": None if state.generator is None else state.generator.initial_seed(),
            "prompt_logprobs": runner.num_prompt_logprobs.get(rid),
            "batch_tokens": batch.token_ids_cpu[i, :n].tolist() if state.prompt_token_ids is not None else None,
            "batch_embeds": batch.req_prompt_embeds[i].tolist() if i in batch.req_prompt_embeds else None,
            "batch_outputs": batch.req_output_token_ids[i] if i < len(batch.req_output_token_ids) else None,
            "batch_length": int(batch.num_prompt_tokens[i]),
            "batch_total": int(batch.num_tokens_no_spec[i]),
            "batch_computed": int(batch.num_computed_tokens_cpu[i]),
            "batch_temperature": float(batch.temperature_cpu[i]),
            "batch_blocks": batch.block_table[0].block_table.np[i, :len(state.block_ids[0])].tolist(),
        }
    # Freeze values now: an in-place correct implementation may mutate lists
    # shared with InputBatch during a later update.
    return json.loads(json.dumps({"states": states, "rows": list(batch.req_ids)}))


def main():
    workload = load_workload()
    runner = make_runner({rid: cached(rid, initial['prompt'], initial['outputs'])
                          for rid, initial in workload['initial'].items()})
    initial_snapshot = snapshot(runner)
    observations = []
    reinsertion = None
    # Inputs come from the grading parent. All state transitions still execute
    # the production runner and InputBatch methods.
    for prescribed in workload['updates']:
        rid, prompt = prescribed['id'], prescribed['prompt']
        embeds = None if prescribed['embeds'] is None else torch.tensor(prescribed['embeds'])
        record = continuation(rid, prompt, prompt_embeds=embeds,
                              marker=prescribed['mm'][0],
                              temperature=prescribed['temperature'],
                              blocks=tuple(prescribed['blocks']),
                              computed=prescribed['computed'])
        record.sampling_params = SamplingParams(temperature=prescribed['temperature'],
                                               seed=prescribed['seed'], max_tokens=50,
                                               prompt_logprobs=prescribed['prompt_logprobs'])
        apply_update(runner, [record])
        observed = snapshot(runner)
        # Simulate the shared output buffer that model sampling would append
        # between continuations; the next update must clear these tokens.
        state = runner.requests[rid]
        index = runner.input_batch.req_id_to_index[rid]
        generated = [30000 + len(observations) * 2, 30001 + len(observations) * 2]
        state.output_token_ids.extend(generated)
        start = state.num_prompt_tokens
        runner.input_batch.token_ids_cpu[index, start:start + len(generated)] = generated
        runner.input_batch.num_tokens_no_spec[index] = state.num_tokens
        observations.append({'input':prescribed, 'observed':observed,
                             'post_output':snapshot(runner)})
        if len(observations) == 3:
            # Remove live rows while retaining cached request state, then
            # reinsert the next continuation through the normal path.
            paused_id = prescribed['id']
            apply_update(runner, [], scheduled_ids=set(runner.requests) - {paused_id})
            reinsertion = {'rows': list(runner.input_batch.req_ids)}
    # Execute production M-RoPE refresh with a deterministic position producer.
    # Model-specific geometry is outside this state-management task.
    class PositionModel:
        supports_mrope = True
        def get_mrope_input_positions(self, tokens, features):
            return torch.tensor([tokens] * 3), len(tokens)
    runner.get_model = lambda: PositionModel()
    runner.uses_mrope = True
    rope = []
    for rope_prompt in workload['mrope']:
        rope_record = continuation(workload['rope_id'], rope_prompt, marker="rope-mm", temperature=0.5,
                                   blocks=([7, 8],), computed=len(rope_prompt)-1)
        apply_update(runner, [rope_record])
        rope_state = runner.requests[workload['rope_id']]
        rope.append({"prompt": rope_prompt, "positions": rope_state.mrope_positions.tolist(),
                     "delta": rope_state.mrope_position_delta})

    # Pooling uses a real pooling request, CachedRequestState and InputBatch;
    # the pooler only supplies its normal no-op parameter update callback.
    pooling = make_runner({})
    pooling.is_pooling_model = True
    pooling.input_batch.is_pooling_model = True
    class Pooler:
        def get_pooling_updates(self, task):
            return SimpleNamespace(apply=lambda params: None)
    pooling.get_model = lambda: SimpleNamespace(pooler=Pooler())
    pooled = []
    for step, pool_input in enumerate(workload['pooling']):
        params = PoolingParams(task="embed", requires_token_ids=pool_input['requires_tokens'])
        record = continuation("pooled", pool_input['prompt'], marker="pool-mm",
                              temperature=0.0, blocks=tuple(pool_input['blocks']), computed=3+step,
                              pooling_params=params)
        record.sampling_params = None
        apply_update(pooling, [record])
        state = pooling.requests['pooled']; batch=pooling.input_batch
        i=batch.req_id_to_index['pooled']
        pooled.append({"length": state.num_prompt_tokens, "prompt":state.prompt_token_ids,
                       "batch_tokens":batch.token_ids_cpu[i,:state.num_prompt_tokens].tolist(),
                       "pooling_state_present": state.pooling_states is not None,
                       "batch_pooling_state_present": batch.pooling_states.get('pooled') is not None,
                       "requires_tokens": batch.pooling_params['pooled'].requires_token_ids,
                       "rows": list(batch.req_ids),
                       "batch_length": int(batch.num_prompt_tokens[i])})
    fresh = workload['finished_reuse']
    apply_update(runner, [], scheduled_ids=set(runner.requests), finished_ids={fresh['id']})
    fresh_embeds = None
    fresh_record = continuation(fresh['id'], fresh['prompt'], marker=fresh['mm'][0],
                                temperature=fresh['temperature'], blocks=tuple(fresh['blocks']),
                                computed=fresh['computed'], prompt_embeds=fresh_embeds)
    fresh_record.sampling_params = SamplingParams(temperature=fresh['temperature'],
                                                  seed=fresh['seed'], max_tokens=50,
                                                  prompt_logprobs=fresh['prompt_logprobs'])
    apply_update(runner, [fresh_record])
    finished_reuse = snapshot(runner)
    with open(os.environ["AIB_OBSERVATIONS"], "w") as handle:
        json.dump({"initial": {rid: v["prompt"] for rid,v in workload["initial"].items()},
                   "initial_snapshot": initial_snapshot,
                   "updates": observations, "mrope": rope, "pooling": pooled,
                   "reinsertion": reinsertion, "finished_reuse": finished_reuse}, handle)
    print("streaming observations captured from production InputBatch")


if __name__ == "__main__":
    main()
