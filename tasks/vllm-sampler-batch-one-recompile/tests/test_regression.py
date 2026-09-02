from __future__ import annotations

import pytest
import torch

from sampler_compile_fixture import run_compile_trace, unwrapped_count
from vllm.v1.sample.sampler import Sampler


def test_batch_one_to_larger_sizes_reuses_one_graph() -> None:
    assert run_compile_trace((1, 2, 8))["compile_counts"] == [1, 1, 1]


def test_hidden_positive_batch_order_reuses_one_graph() -> None:
    assert run_compile_trace((1, 3, 7, 2))["compile_counts"] == [1, 1, 1, 1]


def test_larger_to_one_to_larger_reuses_one_graph() -> None:
    assert run_compile_trace((4, 1, 6))["compile_counts"] == [1, 1, 1]


def test_repeated_batch_one_does_not_recompile() -> None:
    assert run_compile_trace((1, 1, 1))["compile_counts"] == [1, 1, 1]


def test_gathered_logprobs_indices_and_ranks_remain_correct() -> None:
    logprobs = torch.tensor([[0.1, 0.9, 0.3], [0.8, 0.2, 0.4]])
    output = Sampler.gather_logprobs(logprobs, 2, torch.tensor([2, 1], dtype=torch.int64))
    assert output.logprob_token_ids[:, 0].tolist() == [2, 1]
    torch.testing.assert_close(output.logprobs[:, 0], torch.tensor([0.3, 0.2]))
    assert output.selected_token_ranks.tolist() == [2, 3]


def test_direct_rank_count_correctness() -> None:
    x = torch.tensor([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    values = torch.tensor([[2.0], [5.0]])
    assert unwrapped_count(x, values).tolist() == [2, 2]


def test_mismatched_batch_dimensions_are_rejected() -> None:
    with pytest.raises(Exception):
        unwrapped_count(torch.ones(3, 4), torch.ones(1, 1))


def test_empty_batch_is_rejected() -> None:
    with pytest.raises(Exception):
        unwrapped_count(torch.empty(0, 4), torch.empty(0, 1))


def test_output_shapes_and_dtypes_are_preserved() -> None:
    output = run_compile_trace((5,))["outputs"][0]
    assert output.logprob_token_ids.shape == (5, 4)
    assert output.logprobs.shape == (5, 4)
    assert output.selected_token_ranks.shape == (5,)
    assert output.logprob_token_ids.dtype == torch.int32
