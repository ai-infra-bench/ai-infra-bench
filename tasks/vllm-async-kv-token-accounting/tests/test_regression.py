import copy
import json
from functools import partial
from unittest.mock import Mock, patch

import pytest

from vllm.v1.outputs import EMPTY_MODEL_RUNNER_OUTPUT, KVConnectorOutput
from vllm.v1.request import RequestStatus

from . import utils
from .utils import create_model_runner_output, create_request, create_scheduler


def _create_scheduler(tmp_path, monkeypatch, *, block_size=16):
    model_dir = tmp_path / f"tiny-opt-{block_size}"
    model_dir.mkdir(exist_ok=True)
    (model_dir / "config.json").write_text(
        json.dumps(
            {
                "architectures": ["OPTForCausalLM"],
                "model_type": "opt",
                "hidden_size": 64,
                "ffn_dim": 256,
                "num_attention_heads": 4,
                "num_hidden_layers": 2,
                "vocab_size": 256,
                "max_position_embeddings": 256,
                "word_embed_proj_dim": 64,
                "do_layer_norm_before": True,
                "torch_dtype": "float16",
            }
        )
    )
    original_model_config = utils.ModelConfig
    monkeypatch.setattr(
        utils,
        "ModelConfig",
        partial(original_model_config, skip_tokenizer_init=True),
    )
    config = utils.create_vllm_config(
        model=str(model_dir),
        max_model_len=256,
        max_num_batched_tokens=512,
        block_size=block_size,
        kv_load_failure_policy="recompute",
    )
    return create_scheduler(config)


def _configure_connector(scheduler, matches, *, async_load):
    observed_local_hits = {}

    def get_num_new_matched_tokens(request, num_local_tokens):
        observed_local_hits[request.request_id] = num_local_tokens
        return matches[request.request_id], async_load

    scheduler.connector = Mock()
    scheduler.connector.get_num_new_matched_tokens.side_effect = (
        get_num_new_matched_tokens
    )
    scheduler.connector.request_finished.return_value = (False, None)
    scheduler.connector.take_events.return_value = ()
    return observed_local_hits


def _start_async_requests(scheduler, requests, external_matches):
    for request in requests:
        scheduler.add_request(request)
    observed_local_hits = _configure_connector(
        scheduler,
        {
            request.request_id: external_match
            for request, external_match in zip(requests, external_matches)
        },
        async_load=True,
    )
    first_output = scheduler.schedule()
    assert not first_output.scheduled_new_reqs
    assert not first_output.num_scheduled_tokens
    assert [request.status for request in requests] == [
        RequestStatus.WAITING_FOR_REMOTE_KVS
    ] * len(requests)
    return first_output, observed_local_hits


def _report_finished(scheduler, first_output, request_ids):
    scheduler.update_from_output(first_output, EMPTY_MODEL_RUNNER_OUTPUT)
    waiting_output = scheduler.schedule()
    model_output = copy.deepcopy(EMPTY_MODEL_RUNNER_OUTPUT)
    model_output.kv_connector_output = KVConnectorOutput(
        finished_recving=set(request_ids)
    )
    scheduler.update_from_output(waiting_output, model_output)


def _schedule_with_cache_spy(scheduler):
    original_cache_blocks = scheduler.kv_cache_manager.cache_blocks
    calls = []

    def cache_blocks_spy(request, num_tokens):
        calls.append((request.request_id, num_tokens))
        return original_cache_blocks(request, num_tokens)

    with patch.object(
        scheduler.kv_cache_manager,
        "cache_blocks",
        cache_blocks_spy,
    ):
        output = scheduler.schedule()
    return output, calls


def _assert_runnable(output, request, expected_computed, expected_scheduled):
    by_id = {item.req_id: item for item in output.scheduled_new_reqs}
    assert request.status == RequestStatus.RUNNING
    assert by_id[request.request_id].num_computed_tokens == expected_computed
    assert output.num_scheduled_tokens[request.request_id] == expected_scheduled


@pytest.mark.parametrize(
    ("block_size", "prompt_tokens", "matched_tokens"),
    [
        (8, 43, 11),
        (16, 67, 19),
        (16, 70, 37),
        (32, 95, 47),
    ],
)
def test_partial_async_hits_remain_exact(
    tmp_path, monkeypatch, block_size, prompt_tokens, matched_tokens
):
    scheduler = _create_scheduler(tmp_path, monkeypatch, block_size=block_size)
    request = create_request(num_tokens=prompt_tokens, block_size=block_size)
    first_output, observed = _start_async_requests(
        scheduler, [request], [matched_tokens]
    )

    assert observed == {request.request_id: 0}
    _report_finished(scheduler, first_output, [request.request_id])
    runnable_output, cache_calls = _schedule_with_cache_spy(scheduler)

    _assert_runnable(
        runnable_output,
        request,
        matched_tokens,
        prompt_tokens - matched_tokens,
    )
    assert cache_calls == [(request.request_id, matched_tokens)]


def test_concurrent_async_hits_keep_per_request_counts(tmp_path, monkeypatch):
    scheduler = _create_scheduler(tmp_path, monkeypatch)
    cases = [(53, 5), (67, 19), (83, 41)]
    requests = [create_request(num_tokens=prompt) for prompt, _ in cases]
    first_output, _ = _start_async_requests(
        scheduler,
        requests,
        [matched for _, matched in cases],
    )

    _report_finished(
        scheduler,
        first_output,
        [request.request_id for request in requests],
    )
    runnable_output, cache_calls = _schedule_with_cache_spy(scheduler)

    for request, (prompt_tokens, matched_tokens) in zip(requests, cases):
        _assert_runnable(
            runnable_output,
            request,
            matched_tokens,
            prompt_tokens - matched_tokens,
        )
    assert dict(cache_calls) == {
        request.request_id: matched_tokens
        for request, (_, matched_tokens) in zip(requests, cases)
    }


def _prime_local_prefix(scheduler, *, num_tokens, block_size):
    seed = create_request(
        request_id=9000 + block_size,
        num_tokens=num_tokens,
        common_prefix_len=num_tokens,
        block_size=block_size,
    )
    computed_blocks, num_computed_tokens = (
        scheduler.kv_cache_manager.get_computed_blocks(seed)
    )
    assert num_computed_tokens == 0
    allocated = scheduler.kv_cache_manager.allocate_slots(
        seed,
        num_tokens,
        num_new_computed_tokens=0,
        new_computed_blocks=computed_blocks,
    )
    assert allocated is not None
    scheduler.kv_cache_manager.cache_blocks(seed, num_tokens)
    scheduler.kv_cache_manager.free(seed)


def test_local_and_external_hits_are_combined(tmp_path, monkeypatch):
    block_size = 16
    local_tokens = 32
    external_tokens = 9
    prompt_tokens = 83
    scheduler = _create_scheduler(tmp_path, monkeypatch, block_size=block_size)
    _prime_local_prefix(
        scheduler,
        num_tokens=local_tokens,
        block_size=block_size,
    )
    request = create_request(
        num_tokens=prompt_tokens,
        common_prefix_len=local_tokens,
        block_size=block_size,
    )
    first_output, observed = _start_async_requests(
        scheduler, [request], [external_tokens]
    )

    assert observed == {request.request_id: local_tokens}
    _report_finished(scheduler, first_output, [request.request_id])
    runnable_output, cache_calls = _schedule_with_cache_spy(scheduler)
    total_hit = local_tokens + external_tokens

    _assert_runnable(
        runnable_output,
        request,
        total_hit,
        prompt_tokens - total_hit,
    )
    assert cache_calls == [(request.request_id, total_hit)]


@pytest.mark.parametrize(
    ("block_size", "prompt_tokens", "matched_tokens"),
    [(8, 43, 16), (16, 67, 32), (32, 95, 64)],
)
def test_block_aligned_async_hits_stay_correct(
    tmp_path, monkeypatch, block_size, prompt_tokens, matched_tokens
):
    scheduler = _create_scheduler(tmp_path, monkeypatch, block_size=block_size)
    request = create_request(num_tokens=prompt_tokens, block_size=block_size)
    first_output, _ = _start_async_requests(
        scheduler, [request], [matched_tokens]
    )

    _report_finished(scheduler, first_output, [request.request_id])
    runnable_output, cache_calls = _schedule_with_cache_spy(scheduler)

    _assert_runnable(
        runnable_output,
        request,
        matched_tokens,
        prompt_tokens - matched_tokens,
    )
    assert cache_calls == [(request.request_id, matched_tokens)]


@pytest.mark.parametrize(
    ("block_size", "prompt_tokens"),
    [(8, 43), (16, 70), (32, 95)],
)
def test_full_prompt_hits_cache_all_tokens_but_recompute_last(
    tmp_path, monkeypatch, block_size, prompt_tokens
):
    scheduler = _create_scheduler(tmp_path, monkeypatch, block_size=block_size)
    request = create_request(num_tokens=prompt_tokens, block_size=block_size)
    first_output, _ = _start_async_requests(
        scheduler, [request], [prompt_tokens]
    )

    _report_finished(scheduler, first_output, [request.request_id])
    runnable_output, cache_calls = _schedule_with_cache_spy(scheduler)

    _assert_runnable(runnable_output, request, prompt_tokens - 1, 1)
    assert cache_calls == [(request.request_id, prompt_tokens)]


@pytest.mark.parametrize(
    ("block_size", "prompt_tokens", "matched_tokens"),
    [(8, 43, 11), (16, 70, 37)],
)
def test_synchronous_connector_behavior_is_unchanged(
    tmp_path, monkeypatch, block_size, prompt_tokens, matched_tokens
):
    scheduler = _create_scheduler(tmp_path, monkeypatch, block_size=block_size)
    request = create_request(num_tokens=prompt_tokens, block_size=block_size)
    scheduler.add_request(request)
    observed = _configure_connector(
        scheduler,
        {request.request_id: matched_tokens},
        async_load=False,
    )

    output = scheduler.schedule()

    assert observed == {request.request_id: 0}
    _assert_runnable(
        output,
        request,
        matched_tokens,
        prompt_tokens - matched_tokens,
    )


def test_async_load_failure_remains_reschedulable(tmp_path, monkeypatch):
    block_size = 16
    prompt_tokens = 70
    matched_tokens = 37
    scheduler = _create_scheduler(tmp_path, monkeypatch, block_size=block_size)
    request = create_request(num_tokens=prompt_tokens, block_size=block_size)
    first_output, _ = _start_async_requests(
        scheduler, [request], [matched_tokens]
    )

    scheduler.update_from_output(first_output, EMPTY_MODEL_RUNNER_OUTPUT)
    waiting_output = scheduler.schedule()
    (block_ids,) = scheduler.kv_cache_manager.get_block_ids(request.request_id)
    invalid_output = create_model_runner_output(
        [],
        finished_recving=set(),
        invalid_block_ids={block_ids[1]},
    )
    scheduler.update_from_output(waiting_output, invalid_output)
    assert request.status == RequestStatus.WAITING_FOR_REMOTE_KVS

    waiting_output = scheduler.schedule()
    finished_output = copy.deepcopy(EMPTY_MODEL_RUNNER_OUTPUT)
    finished_output.kv_connector_output = KVConnectorOutput(
        finished_recving={request.request_id}
    )
    scheduler.update_from_output(waiting_output, finished_output)
    runnable_output, cache_calls = _schedule_with_cache_spy(scheduler)

    expected_valid_tokens = block_size
    _assert_runnable(
        runnable_output,
        request,
        expected_valid_tokens,
        prompt_tokens - expected_valid_tokens,
    )
    assert cache_calls == [(request.request_id, expected_valid_tokens)]
    assert request.request_id not in scheduler.failed_recving_kv_req_ids
    assert request.request_id not in scheduler.finished_recving_kv_req_ids
