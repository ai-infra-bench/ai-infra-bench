from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest
import torch

from vllm.v1.executor import ray_utils
from vllm.v1.outputs import LogprobsLists, LogprobsTensors, ModelRunnerOutput


@dataclass(frozen=True)
class ArrayProfile:
    rows: int
    cols: int
    token_dtype: np.dtype
    logprob_dtype: np.dtype
    rank_dtype: np.dtype
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


def _make_output(profile: ArrayProfile, readonly=(True, True, True)):
    size = profile.rows * profile.cols
    token_ids = (
        np.arange(size, dtype=profile.token_dtype).reshape(profile.rows, profile.cols)
        + profile.offset
    )
    logprobs = (
        np.linspace(-3.0, -0.01, size, dtype=profile.logprob_dtype).reshape(
            profile.rows, profile.cols
        )
        - profile.offset / 100
    )
    ranks = np.arange(profile.rows, dtype=profile.rank_dtype) + profile.offset
    arrays = (token_ids, logprobs, ranks)
    for array, make_readonly in zip(arrays, readonly):
        if make_readonly:
            array.setflags(write=False)
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
        logprobs=LogprobsLists(
            token_ids,
            logprobs,
            ranks,
            list(range(profile.rows + 1)),
        ),
        prompt_logprobs_dict={"prompt": prompt},
    )
    return output, arrays, prompt


def _through_result_boundary(monkeypatch, output):
    monkeypatch.setattr(ray_utils, "ray", _RayResultBoundary)
    return ray_utils.FutureWrapper(_Ref(output)).result(timeout=1)


def _assert_values(actual, expected):
    assert actual.logprobs is not None
    actual_arrays = actual.logprobs[:3]
    for got, want in zip(actual_arrays, expected):
        np.testing.assert_array_equal(got, want)
        assert got.dtype == want.dtype
        assert got.shape == want.shape
    return actual_arrays


PROFILES = [
    ArrayProfile(1, 1, np.dtype("int32"), np.dtype("float32"), np.dtype("int16"), 3),
    ArrayProfile(2, 4, np.dtype("int64"), np.dtype("float64"), np.dtype("int32"), 11),
    ArrayProfile(5, 3, np.dtype("uint32"), np.dtype("float32"), np.dtype("int64"), 29),
    ArrayProfile(17, 9, np.dtype("int32"), np.dtype("float64"), np.dtype("int16"), 41),
]


@pytest.mark.parametrize("profile", PROFILES)
def test_borrowed_readonly_logprob_memory_is_released(monkeypatch, profile):
    output, original_arrays, prompt = _make_output(profile)
    result = _through_result_boundary(monkeypatch, output)

    actual_arrays = _assert_values(result, original_arrays)
    for actual, original in zip(actual_arrays, original_arrays):
        assert not np.shares_memory(actual, original)
    assert result.logprobs.cu_num_generated_tokens == list(range(profile.rows + 1))
    actual_prompt = result.prompt_logprobs_dict["prompt"]
    torch.testing.assert_close(actual_prompt.logprob_token_ids, prompt.logprob_token_ids)
    torch.testing.assert_close(actual_prompt.logprobs, prompt.logprobs)
    torch.testing.assert_close(
        actual_prompt.selected_token_ranks,
        prompt.selected_token_ranks,
    )


@pytest.mark.parametrize(
    "readonly",
    [
        (True, False, False),
        (False, True, False),
        (False, False, True),
        (False, False, False),
    ],
)
def test_mixed_ownership_preserves_values_without_copy_policy(
    monkeypatch, readonly
):
    output, original_arrays, _prompt = _make_output(PROFILES[1], readonly=readonly)
    result = _through_result_boundary(monkeypatch, output)

    actual_arrays = _assert_values(result, original_arrays)
    for actual, original, was_readonly in zip(
        actual_arrays, original_arrays, readonly
    ):
        if was_readonly:
            assert not np.shares_memory(actual, original)


def test_empty_logprob_arrays_are_valid(monkeypatch):
    token_ids = np.empty((0, 0), dtype=np.int32)
    logprobs = np.empty((0, 0), dtype=np.float32)
    ranks = np.empty((0,), dtype=np.int16)
    for array in (token_ids, logprobs, ranks):
        array.setflags(write=False)
    output = ModelRunnerOutput(
        req_ids=[],
        req_id_to_index={},
        logprobs=LogprobsLists(token_ids, logprobs, ranks, [0]),
    )
    result = _through_result_boundary(monkeypatch, output)
    arrays = _assert_values(result, (token_ids, logprobs, ranks))
    assert all(not np.shares_memory(actual, before) for actual, before in zip(arrays, (token_ids, logprobs, ranks)))


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


def test_result_object_identity_and_array_writeability_are_not_requirements(
    monkeypatch,
):
    output, original_arrays, _prompt = _make_output(PROFILES[0])
    result = _through_result_boundary(monkeypatch, output)
    actual_arrays = _assert_values(result, original_arrays)
    assert all(not np.shares_memory(actual, before) for actual, before in zip(actual_arrays, original_arrays))
