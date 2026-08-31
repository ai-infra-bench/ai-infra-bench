import json

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
                "max_position_embeddings": 256,
                "word_embed_proj_dim": 64,
                "do_layer_norm_before": True,
                "torch_dtype": "float16",
            }
        )
    )
    return str(model_dir)


def _scheduler(tmp_path, *, enable_prefix_caching=False):
    return create_scheduler(
        model=_tiny_model(tmp_path),
        max_num_batched_tokens=32,
        max_model_len=128,
        enable_chunked_prefill=True,
        enable_prefix_caching=enable_prefix_caching,
        num_blocks=13,
        block_size=16,
        skip_tokenizer_init=True,
    )


def _advance_through_prefill(scheduler, request):
    while request.num_output_tokens == 0:
        output = scheduler.schedule()
        assert request.request_id in output.num_scheduled_tokens
        sampled = (
            [1000]
            if request.num_computed_tokens >= request.num_prompt_tokens
            else []
        )
        model_output = ModelRunnerOutput(
            req_ids=[request.request_id],
            req_id_to_index={request.request_id: 0},
            sampled_token_ids=[sampled],
            logprobs=None,
            prompt_logprobs_dict={},
            pooler_output=[],
        )
        scheduler.update_from_output(output, model_output)


def _add_running_incumbent(scheduler):
    incumbent = create_requests(
        num_requests=1,
        num_tokens=96,
        max_tokens=16,
        req_ids=["incumbent"],
    )[0]
    scheduler.add_request(incumbent)
    _advance_through_prefill(scheduler, incumbent)
    assert incumbent.status == RequestStatus.RUNNING
    return incumbent


def test_long_prompt_that_cannot_fit_remains_waiting(tmp_path):
    scheduler = _scheduler(tmp_path)
    incumbent = _add_running_incumbent(scheduler)
    request = create_requests(num_requests=1, num_tokens=112, max_tokens=4)[0]
    scheduler.add_request(request)

    output = scheduler.schedule()

    assert request.request_id not in output.num_scheduled_tokens
    assert not output.scheduled_new_reqs
    assert request.status == RequestStatus.WAITING
    assert incumbent.request_id in output.num_scheduled_tokens
    assert scheduler.running == [incumbent]


def test_prompt_that_fits_is_still_admitted(tmp_path):
    scheduler = _scheduler(tmp_path)
    _add_running_incumbent(scheduler)
    request = create_requests(num_requests=1, num_tokens=80, max_tokens=4)[0]
    scheduler.add_request(request)

    output = scheduler.schedule()

    assert output.num_scheduled_tokens[request.request_id] > 0
    assert output.scheduled_new_reqs[0].req_id == request.request_id
    assert request.status == RequestStatus.RUNNING


def test_cached_prefix_credit_can_make_long_prompt_admissible(tmp_path):
    scheduler = _scheduler(tmp_path, enable_prefix_caching=True)
    seed = create_requests(
        num_requests=1,
        num_tokens=64,
        max_tokens=1,
        same_prompt=True,
        req_ids=["seed"],
    )[0]
    scheduler.add_request(seed)
    _advance_through_prefill(scheduler, seed)
    assert seed.is_finished()

    request = create_requests(
        num_requests=1,
        num_tokens=160,
        max_tokens=4,
        same_prompt=True,
        req_ids=["target"],
    )
    request = request[0]
    scheduler.add_request(request)

    output = scheduler.schedule()

    assert output.num_scheduled_tokens[request.request_id] == 32
    assert output.scheduled_new_reqs[0].req_id == request.request_id
    assert output.scheduled_new_reqs[0].num_computed_tokens >= 48
    assert request.status == RequestStatus.RUNNING
