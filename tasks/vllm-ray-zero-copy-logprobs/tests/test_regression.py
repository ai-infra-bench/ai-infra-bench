from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pytest
import torch

from vllm.entrypoints.openai.completion.protocol import CompletionRequest
from vllm.entrypoints.openai.completion.serving import OpenAIServingCompletion
from vllm.entrypoints.openai.engine.protocol import RequestResponseMetadata
from vllm.logprobs import Logprob
from vllm.outputs import CompletionOutput, RequestOutput
from vllm.v1.engine.logprobs import LogprobsProcessor
from vllm.v1.executor import ray_utils
from vllm.v1.outputs import LogprobsTensors, ModelRunnerOutput


@dataclass(frozen=True)
class PayloadProfile:
    rows: int
    cols: int
    token_dtype: torch.dtype
    logprob_dtype: torch.dtype
    rank_dtype: torch.dtype
    offset: int


class _Ref:
    def __init__(self, value):
        self.value = value


class _RayResultBoundary:
    @staticmethod
    def get(refs, timeout=None):
        del timeout
        if isinstance(refs, list):
            return [ref.value for ref in refs]
        return refs.value


def _make_output(profile: PayloadProfile):
    size = profile.rows * profile.cols
    token_ids = (
        torch.arange(size, dtype=profile.token_dtype).reshape(
            profile.rows, profile.cols
        )
        + profile.offset
    )
    logprobs = (
        torch.linspace(-3.0, -0.01, size, dtype=profile.logprob_dtype).reshape(
            profile.rows, profile.cols
        )
        - profile.offset / 100
    )
    ranks = torch.arange(profile.rows, dtype=profile.rank_dtype) + profile.offset
    cu_tokens = list(range(profile.rows + 1))
    tensor_payload = LogprobsTensors(token_ids, logprobs, ranks, cu_tokens)
    expected = tuple(tensor.cpu().numpy().copy() for tensor in tensor_payload[:3])

    prompt = LogprobsTensors.empty_cpu(profile.rows, profile.cols)
    prompt.logprob_token_ids.fill_(profile.offset)
    prompt.logprobs.fill_(-profile.offset / 10)
    prompt.selected_token_ranks.fill_(profile.offset)
    output = ModelRunnerOutput(
        req_ids=[f"req-{profile.offset}-{index}" for index in range(profile.rows)],
        req_id_to_index={
            f"req-{profile.offset}-{index}": index
            for index in range(profile.rows)
        },
        sampled_token_ids=[
            [int(token_id)] for token_id in expected[0][:, 0]
        ],
        logprobs=tensor_payload.tolists(),
        prompt_logprobs_dict={"prompt": prompt},
    )
    return output, expected, prompt


def _through_result_boundary(monkeypatch, output):
    monkeypatch.setattr(ray_utils, "ray", _RayResultBoundary)
    return ray_utils.FutureWrapper(_Ref(output)).result(timeout=1)


def _assert_values(actual, expected):
    assert actual.logprobs is not None
    converted = tuple(np.asarray(value) for value in actual.logprobs[:3])
    np.testing.assert_array_equal(converted[0], expected[0])
    np.testing.assert_allclose(converted[1], expected[1], rtol=1e-6, atol=1e-7)
    np.testing.assert_array_equal(converted[2], expected[2])
    return converted


PROFILES = [
    PayloadProfile(1, 1, torch.int32, torch.float32, torch.int16, 3),
    PayloadProfile(2, 4, torch.int64, torch.float64, torch.int32, 11),
    PayloadProfile(5, 3, torch.int32, torch.float32, torch.int64, 29),
    PayloadProfile(17, 9, torch.int32, torch.float64, torch.int16, 41),
]


@pytest.mark.parametrize("profile", PROFILES)
def test_logprob_values_survive_result_boundary(monkeypatch, profile):
    output, expected, prompt = _make_output(profile)
    result = _through_result_boundary(monkeypatch, output)

    _assert_values(result, expected)
    assert result.logprobs.cu_num_generated_tokens == list(range(profile.rows + 1))
    assert result.req_ids == output.req_ids
    assert result.req_id_to_index == output.req_id_to_index
    assert result.sampled_token_ids == output.sampled_token_ids
    assert result.sampled_token_ids == [
        [int(token_id)] for token_id in expected[0][:, 0]
    ]
    actual_prompt = result.prompt_logprobs_dict["prompt"]
    torch.testing.assert_close(actual_prompt.logprob_token_ids, prompt.logprob_token_ids)
    torch.testing.assert_close(actual_prompt.logprobs, prompt.logprobs)
    torch.testing.assert_close(
        actual_prompt.selected_token_ranks,
        prompt.selected_token_ranks,
    )


@pytest.mark.parametrize("profile", PROFILES)
def test_repeated_results_do_not_mix_payloads(monkeypatch, profile):
    first, first_expected, _ = _make_output(profile)
    second_profile = replace(profile, offset=profile.offset + 100)
    second, second_expected, _ = _make_output(second_profile)

    first_result = _through_result_boundary(monkeypatch, first)
    second_result = _through_result_boundary(monkeypatch, second)

    first_values = _assert_values(first_result, first_expected)
    second_values = _assert_values(second_result, second_expected)
    assert first_result.req_ids != second_result.req_ids
    assert first_result.sampled_token_ids == [
        [int(token_id)] for token_id in first_expected[0][:, 0]
    ]
    assert second_result.sampled_token_ids == [
        [int(token_id)] for token_id in second_expected[0][:, 0]
    ]
    assert any(
        not np.array_equal(before, after)
        for before, after in zip(first_values, second_values)
    )


def test_empty_logprob_payload_is_valid(monkeypatch):
    tensor_payload = LogprobsTensors(
        torch.empty((0, 0), dtype=torch.int32),
        torch.empty((0, 0), dtype=torch.float32),
        torch.empty((0,), dtype=torch.int16),
        [0],
    )
    output = ModelRunnerOutput(
        req_ids=[],
        req_id_to_index={},
        logprobs=tensor_payload.tolists(),
    )
    result = _through_result_boundary(monkeypatch, output)
    assert result.logprobs is not None
    assert all(len(value) == 0 for value in result.logprobs[:3])
    assert result.logprobs.cu_num_generated_tokens == [0]


def test_none_logprobs_and_unrelated_fields_are_preserved(monkeypatch):
    output = ModelRunnerOutput(
        req_ids=["no-logprobs"],
        req_id_to_index={"no-logprobs": 0},
        sampled_token_ids=[[17]],
        logprobs=None,
        prompt_logprobs_dict={},
    )
    result = _through_result_boundary(monkeypatch, output)
    assert result.req_ids == ["no-logprobs"]
    assert result.req_id_to_index == {"no-logprobs": 0}
    assert result.sampled_token_ids == [[17]]
    assert result.logprobs is None


def test_downstream_logprob_processing_accepts_result_payload(monkeypatch):
    output, expected, _ = _make_output(PROFILES[1])
    result = _through_result_boundary(monkeypatch, output)
    _assert_values(result, expected)

    processor = LogprobsProcessor(
        tokenizer=None,
        logprobs=[],
        prompt_logprobs=None,
        cumulative_logprob=0.0,
        num_logprobs=PROFILES[1].cols - 1,
        num_prompt_logprobs=None,
    )
    processor._update_sample_logprobs(result.logprobs)

    assert len(processor.logprobs) == PROFILES[1].rows
    expected_cumulative = float(expected[1][:, 0].sum())
    assert processor.cumulative_logprob == pytest.approx(expected_cumulative)


def test_completion_response_preserves_text_tokens_and_logprobs():
    output = CompletionOutput(
        index=0,
        text=" Photo uploads close the app unexpectedly.",
        token_ids=[101, 202],
        cumulative_logprob=-1.25,
        logprobs=[
            {
                101: Logprob(logprob=-0.5, rank=1),
                111: Logprob(logprob=-1.5, rank=2),
            },
            {
                202: Logprob(logprob=-0.75, rank=1),
                212: Logprob(logprob=-1.75, rank=2),
            },
        ],
        finish_reason="length",
    )
    final_result = RequestOutput(
        request_id="completion-contract",
        prompt="Summarize the ticket.",
        prompt_token_ids=[7, 8, 9],
        prompt_logprobs=None,
        outputs=[output],
        finished=True,
    )
    request = CompletionRequest(
        prompt="Summarize the ticket.",
        max_tokens=2,
        logprobs=1,
        return_tokens_as_token_ids=True,
        return_token_ids=True,
    )
    serving = object.__new__(OpenAIServingCompletion)
    serving.enable_prompt_tokens_details = False
    request_metadata = RequestResponseMetadata(request_id="completion-contract")

    response = serving.request_output_to_completion_response(
        [final_result],
        request,
        request_id="cmpl-contract",
        created_time=1234567890,
        model_name="offline-model",
        tokenizer=None,
        request_metadata=request_metadata,
    )

    assert response.id == "cmpl-contract"
    assert response.object == "text_completion"
    assert response.created == 1234567890
    assert response.model == "offline-model"
    assert len(response.choices) == 1
    choice = response.choices[0]
    assert choice.text == output.text
    assert choice.token_ids == [101, 202]
    assert choice.finish_reason == "length"
    assert choice.logprobs is not None
    assert choice.logprobs.text_offset == [0, len("token_id:101")]
    assert choice.logprobs.tokens == ["token_id:101", "token_id:202"]
    assert choice.logprobs.token_logprobs == pytest.approx([-0.5, -0.75])
    assert choice.logprobs.top_logprobs == [
        {"token_id:101": -0.5, "token_id:111": -1.5},
        {"token_id:202": -0.75, "token_id:212": -1.75},
    ]
    assert response.usage.prompt_tokens == 3
    assert response.usage.completion_tokens == 2
    assert response.usage.total_tokens == 5
    assert request_metadata.final_usage_info == response.usage

    no_logprobs_output = CompletionOutput(
        index=0,
        text=" Existing no-logprobs behavior remains intact.",
        token_ids=[303],
        cumulative_logprob=None,
        logprobs=None,
        finish_reason="stop",
    )
    no_logprobs_result = RequestOutput(
        request_id="completion-no-logprobs",
        prompt="Continue.",
        prompt_token_ids=[10],
        prompt_logprobs=None,
        outputs=[no_logprobs_output],
        finished=True,
    )
    no_logprobs_metadata = RequestResponseMetadata(
        request_id="completion-no-logprobs"
    )
    no_logprobs_response = serving.request_output_to_completion_response(
        [no_logprobs_result],
        CompletionRequest(
            prompt="Continue.",
            max_tokens=1,
            logprobs=None,
            return_token_ids=True,
        ),
        request_id="cmpl-no-logprobs",
        created_time=1234567891,
        model_name="offline-model",
        tokenizer=None,
        request_metadata=no_logprobs_metadata,
    )

    no_logprobs_choice = no_logprobs_response.choices[0]
    assert no_logprobs_choice.text == no_logprobs_output.text
    assert no_logprobs_choice.token_ids == [303]
    assert no_logprobs_choice.logprobs is None
    assert no_logprobs_response.usage.prompt_tokens == 1
    assert no_logprobs_response.usage.completion_tokens == 1
    assert no_logprobs_response.usage.total_tokens == 2
    assert no_logprobs_metadata.final_usage_info == no_logprobs_response.usage
