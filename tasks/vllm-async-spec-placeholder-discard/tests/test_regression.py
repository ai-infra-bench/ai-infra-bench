import json

import pytest
from vllm.v1.core.sched.output import CachedRequestData, SchedulerOutput
from vllm.v1.outputs import ModelRunnerOutput
from vllm.v1.request import RequestStatus

from .utils import create_requests, create_scheduler


def _tiny_model(tmp_path):
    model_dir = tmp_path / "tiny-opt"
    model_dir.mkdir()
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
                "max_position_embeddings": 1024,
                "word_embed_proj_dim": 64,
                "do_layer_norm_before": True,
                "torch_dtype": "float16",
            }
        )
    )
    return str(model_dir)


def _scheduler_and_requests(tmp_path, count=1, max_spec_tokens=8):
    scheduler = create_scheduler(
        model=_tiny_model(tmp_path),
        async_scheduling=True,
        skip_tokenizer_init=True,
        max_model_len=1024,
        max_num_batched_tokens=1024,
    )
    scheduler.num_spec_tokens = max_spec_tokens
    requests = create_requests(num_requests=count, max_tokens=128)
    for request in requests:
        request.num_computed_tokens = request.num_tokens
        scheduler.requests[request.request_id] = request
        scheduler.running.append(request)
        request.status = RequestStatus.RUNNING
    return scheduler, requests


def _runner_frame(cases):
    num_scheduled_tokens = {}
    scheduled_spec_decode_tokens = {}
    sampled_token_ids = []
    request_ids = []
    for request, num_drafts, num_accepted in cases:
        request_ids.append(request.request_id)
        num_scheduled_tokens[request.request_id] = num_drafts + 1
        if num_drafts:
            scheduled_spec_decode_tokens[request.request_id] = list(
                range(100, 100 + num_drafts)
            )
        sampled_token_ids.append(
            list(range(900, 900 + 1 + num_accepted))
        )

    scheduler_output = SchedulerOutput(
        scheduled_new_reqs=[],
        scheduled_cached_reqs=CachedRequestData.make_empty(),
        num_scheduled_tokens=num_scheduled_tokens,
        total_num_scheduled_tokens=sum(num_scheduled_tokens.values()),
        scheduled_encoder_inputs={},
        scheduled_spec_decode_tokens=scheduled_spec_decode_tokens,
        num_common_prefix_blocks=[],
        finished_req_ids=set(),
        free_encoder_mm_hashes=[],
    )
    model_runner_output = ModelRunnerOutput(
        req_ids=request_ids,
        req_id_to_index={req_id: index for index, req_id in enumerate(request_ids)},
        sampled_token_ids=sampled_token_ids,
        logprobs=None,
        prompt_logprobs_dict={},
        pooler_output=[],
    )
    return scheduler_output, model_runner_output


@pytest.mark.parametrize(
    "num_drafts,num_accepted,fresh_placeholders,discard_count",
    [
        (1, 0, 1, 1),
        (2, 0, 2, 3),
        (3, 1, 1, 4),
        (5, 0, 1, 5),
        (5, 3, 2, 6),
        (7, 2, 4, 8),
    ],
    ids=[
        "one-draft",
        "two-drafts",
        "partial-three",
        "all-rejected-five",
        "partial-five",
        "partial-seven",
    ],
)
def test_stale_spec_frame_preserves_resumed_state(
    tmp_path,
    num_drafts,
    num_accepted,
    fresh_placeholders,
    discard_count,
):
    scheduler, (request,) = _scheduler_and_requests(
        tmp_path,
        max_spec_tokens=num_drafts,
    )
    request.num_output_placeholders = fresh_placeholders
    request.async_tokens_to_discard = discard_count
    computed_before = request.num_computed_tokens
    output_tokens_before = list(request.output_token_ids)
    scheduler_output, model_runner_output = _runner_frame(
        [(request, num_drafts, num_accepted)]
    )

    scheduler.update_from_output(scheduler_output, model_runner_output)

    assert request.num_output_placeholders == fresh_placeholders
    assert request.num_computed_tokens == computed_before
    assert request.async_tokens_to_discard == discard_count - 1
    assert list(request.output_token_ids) == output_tokens_before
    assert request.status == RequestStatus.RUNNING


@pytest.mark.parametrize(
    "num_drafts,num_accepted",
    [(1, 0), (3, 1), (5, 0), (7, 7)],
    ids=["one-rejected", "partial", "all-rejected", "all-accepted"],
)
def test_ordinary_spec_frame_keeps_rejection_accounting(
    tmp_path,
    num_drafts,
    num_accepted,
):
    scheduler, (request,) = _scheduler_and_requests(
        tmp_path,
        max_spec_tokens=num_drafts,
    )
    request.num_output_placeholders = num_drafts + 1
    request.async_tokens_to_discard = 0
    computed_before = request.num_computed_tokens
    scheduler_output, model_runner_output = _runner_frame(
        [(request, num_drafts, num_accepted)]
    )

    scheduler.update_from_output(scheduler_output, model_runner_output)

    assert request.num_output_placeholders == 0
    assert request.num_computed_tokens == computed_before - (
        num_drafts - num_accepted
    )
    assert request.async_tokens_to_discard == 0
    assert len(request.output_token_ids) == num_accepted + 1
    assert request.status == RequestStatus.RUNNING


def test_stale_and_ordinary_requests_are_accounted_independently(tmp_path):
    scheduler, requests = _scheduler_and_requests(tmp_path, count=2)
    stale, ordinary = requests
    stale.num_output_placeholders = 2
    stale.async_tokens_to_discard = 4
    ordinary.num_output_placeholders = 4
    ordinary.async_tokens_to_discard = 0
    stale_computed = stale.num_computed_tokens
    ordinary_computed = ordinary.num_computed_tokens
    scheduler_output, model_runner_output = _runner_frame(
        [(stale, 5, 1), (ordinary, 3, 1)]
    )

    scheduler.update_from_output(scheduler_output, model_runner_output)

    assert stale.num_output_placeholders == 2
    assert stale.num_computed_tokens == stale_computed
    assert stale.async_tokens_to_discard == 3
    assert list(stale.output_token_ids) == []
    assert ordinary.num_output_placeholders == 0
    assert ordinary.num_computed_tokens == ordinary_computed - 2
    assert ordinary.async_tokens_to_discard == 0
    assert len(ordinary.output_token_ids) == 2


def test_empty_runner_result_does_not_consume_discard_budget(tmp_path):
    scheduler, (request,) = _scheduler_and_requests(tmp_path, max_spec_tokens=5)
    request.num_output_placeholders = 3
    request.async_tokens_to_discard = 2
    computed_before = request.num_computed_tokens
    scheduler_output, model_runner_output = _runner_frame([(request, 5, 0)])
    model_runner_output.sampled_token_ids = [[]]

    scheduler.update_from_output(scheduler_output, model_runner_output)

    assert request.num_output_placeholders == 3
    assert request.num_computed_tokens == computed_before
    assert request.async_tokens_to_discard == 2
    assert request.status == RequestStatus.RUNNING


def test_non_speculative_async_frame_is_unchanged(tmp_path):
    scheduler, (request,) = _scheduler_and_requests(tmp_path)
    request.num_output_placeholders = 1
    request.async_tokens_to_discard = 0
    scheduler_output, model_runner_output = _runner_frame([(request, 0, 0)])

    scheduler.update_from_output(scheduler_output, model_runner_output)

    assert request.num_output_placeholders == 0
    assert request.async_tokens_to_discard == 0
    assert len(request.output_token_ids) == 1
    assert request.status == RequestStatus.RUNNING
