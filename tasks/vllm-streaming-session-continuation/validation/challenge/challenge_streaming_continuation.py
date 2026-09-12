#!/usr/bin/env python3
"""Independent fresh partial-absorption and three-session challenge.
The production update lifecycle and InputBatch run for real on CPU. The input
scheduler records and PP-last-rank flag are substituted; no GPU execution or
model output determines this state-management boundary. Cached-state object
identity is deliberately not scored.
"""
from __future__ import annotations

import json
import sys
import traceback
from types import SimpleNamespace

import torch

from vllm.sampling_params import SamplingParams
from vllm.v1.core.sched.output import CachedRequestData, NewRequestData
from vllm.v1.worker.gpu_input_batch import CachedRequestState, InputBatch
import vllm.v1.worker.gpu_model_runner as runner_module
from vllm.v1.worker.gpu_model_runner import GPUModelRunner


def check_batch(runner):
    batch=runner.input_batch
    assert len(batch.req_ids)==len(set(batch.req_ids))==len(runner.requests)
    for rid,state in runner.requests.items():
        i=batch.req_id_to_index[rid]
        assert batch.num_prompt_tokens[i]==state.num_prompt_tokens
        assert batch.token_ids_cpu[i,:state.num_prompt_tokens].tolist()==state.prompt_token_ids
        assert batch.req_output_token_ids[i]==state.output_token_ids


def cached(req_id, prompt, outputs, *, marker=None):
    return CachedRequestState(
        req_id=req_id,
        prompt_token_ids=list(prompt),
        mm_features=[] if marker is None else [marker],
        sampling_params=SamplingParams(temperature=0.0, max_tokens=8),
        generator=None,
        block_ids=([4],),
        num_computed_tokens=len(prompt),
        output_token_ids=list(outputs),
    )


def continuation(req_id, prompt, *, marker, temperature, blocks, computed,
                 prompt_embeds=None, pooling_params=None):
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


def scheduler_output(records, scheduled_ids):
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
        finished_req_ids=set(),
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
    runner.input_batch = InputBatch(8, 128, 128, torch.device("cpu"), False, 32000, [16], [16])
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
    runner._init_mrope_positions = lambda state: None
    return runner


def apply_update(runner, records):
    previous = runner_module.get_pp_group
    runner_module.get_pp_group = lambda: SimpleNamespace(is_last_rank=True)
    try:
        scheduled_ids = set(runner.requests) | {r.req_id for r in records}
        GPUModelRunner._update_states(runner, scheduler_output(records, scheduled_ids))
    finally:
        runner_module.get_pp_group = previous


def challenge_partial_absorption_two_of_four() -> dict:
    # Prior outputs [90,91,92,93]; new prompt absorbs the first TWO (90,91).
    # The un-absorbed tail [92,93] must NOT survive.
    req_id = "chal-partial-2of4"
    original = cached(req_id, [5, 6, 7], [90, 91, 92, 93])
    runner = make_runner({req_id: original})
    new_prompt = [5, 6, 7, 90, 91]
    blocks = ([21, 22],)
    apply_update(runner, [continuation(req_id, new_prompt, marker=object(),
                                       temperature=0.3, blocks=blocks,
                                       computed=len(new_prompt) - 1)])
    original = runner.requests[req_id]
    check_batch(runner)
    assert original.prompt_token_ids == new_prompt
    assert original.num_prompt_tokens == len(new_prompt)
    assert original.output_token_ids == [], (
        f"stale output tail survived: {original.output_token_ids!r}"
    )
    assert original.block_ids == blocks
    return {"absorbed": 2, "prior_len": 4, "cleared": True}


def challenge_three_session_interleave() -> dict:
    ids = ["chal-x", "chal-y", "chal-z"]
    st = {
        ids[0]: cached(ids[0], [1, 2], [40]),
        ids[1]: cached(ids[1], [3, 4, 5], [50, 51]),
        ids[2]: cached(ids[2], [6], [60, 61, 62]),
    }
    runner = make_runner(st)
    x_snapshot = list(st[ids[0]].prompt_token_ids)
    z_snapshot = list(st[ids[2]].prompt_token_ids)
    # Continue only the middle session; the other two must be untouched.
    y_blocks = ([31, 32],)
    y_marker = object()
    apply_update(runner, [continuation(ids[1], [3, 4, 5, 50, 51, 52], marker=y_marker,
                                       temperature=0.6, blocks=y_blocks, computed=5)])
    st = runner.requests
    check_batch(runner)
    assert st[ids[1]].prompt_token_ids == [3, 4, 5, 50, 51, 52]
    assert st[ids[1]].output_token_ids == []
    assert st[ids[1]].mm_features == [y_marker]
    assert st[ids[1]].block_ids == y_blocks
    assert st[ids[0]].prompt_token_ids == x_snapshot
    assert st[ids[2]].prompt_token_ids == z_snapshot
    return {"sessions": 3, "continued": 1, "others_unchanged": True}


def main() -> None:
    stages = {
        "partial_absorption_two_of_four": challenge_partial_absorption_two_of_four,
        "three_session_interleave": challenge_three_session_interleave,
    }
    passed = {}
    failures = {}
    for name, fn in stages.items():
        try:
            passed[name] = fn()
        except Exception as exc:  # noqa: BLE001 - report every stage
            failures[name] = {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
    print(json.dumps({"passed": passed, "failures": failures}, indent=2, sort_keys=True))
    if failures:
        print("CHALLENGE_STREAMING_CONTINUATION=FAIL")
        sys.exit(1)
    print("CHALLENGE_STREAMING_CONTINUATION=PASS")


if __name__ == "__main__":
    main()
