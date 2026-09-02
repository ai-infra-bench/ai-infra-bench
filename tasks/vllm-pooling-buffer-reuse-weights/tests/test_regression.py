from __future__ import annotations

import torch

from pooling_fixture import (
    ConsumptionModel,
    PackedWeightModel,
    SimpleModel,
    buffer_reusing_iterator,
    expected_parameters,
    load_parameters,
    make_pooling_model,
    mismatches,
    packed_weights,
    simple_weights,
)


def test_buffer_reuse_loads_every_simple_parameter() -> None:
    weights = simple_weights()
    _, actual = load_parameters(SimpleModel, weights, reuse=True)
    assert not mismatches(actual, expected_parameters(SimpleModel, weights))


def test_buffer_reuse_preserves_pooling_output() -> None:
    weights = simple_weights()
    reference = SimpleModel()
    reference.load_weights(weights.items())
    candidate, _ = load_parameters(SimpleModel, weights, reuse=True)
    value = torch.tensor([[0.5, -1.0, 2.0, 3.0]])
    torch.testing.assert_close(candidate.model(value), reference.model(value))


def test_probed_packed_shard_is_cloned_before_buffer_reuse() -> None:
    weights = packed_weights()
    _, actual = load_parameters(PackedWeightModel, weights, reuse=True)
    assert not mismatches(actual, expected_parameters(PackedWeightModel, weights))


def test_ordinary_iterator_remains_correct() -> None:
    weights = simple_weights()
    _, actual = load_parameters(SimpleModel, weights, reuse=False)
    assert not mismatches(actual, expected_parameters(SimpleModel, weights))


def test_ordinary_packed_iterator_remains_correct() -> None:
    weights = packed_weights()
    _, actual = load_parameters(PackedWeightModel, weights, reuse=False)
    assert not mismatches(actual, expected_parameters(PackedWeightModel, weights))


def test_relative_checkpoint_names_keep_supported_prefix_mapping() -> None:
    relative = simple_weights(prefix="")
    expected = expected_parameters(SimpleModel, relative)
    _, actual = load_parameters(SimpleModel, relative, reuse=True)
    assert not mismatches(actual, expected)


def test_missing_output_head_stays_missing() -> None:
    model, _ = load_parameters(SimpleModel, simple_weights(), reuse=True)
    assert not any(name.startswith("lm_head") for name, _ in model.named_parameters())


def test_unknown_checkpoint_weight_is_ignored_without_corrupting_known_weights() -> None:
    weights = simple_weights()
    weights["model.unknown.weight"] = torch.randn(8, 8)
    expected = expected_parameters(SimpleModel, weights)
    _, actual = load_parameters(SimpleModel, weights, reuse=True)
    assert not mismatches(actual, expected)


def test_loader_does_not_consume_whole_stream_before_parent_reads() -> None:
    weights = simple_weights()
    model = make_pooling_model(ConsumptionModel)
    model.first_consumed_count = None
    model.yielded_count = 0
    model.load_weights(buffer_reusing_iterator(weights, model=model))
    assert model.first_consumed_count is not None
    assert model.first_consumed_count < len(weights)


def test_repeated_buffer_reuse_loads_are_stable() -> None:
    weights = simple_weights()
    first_model, first = load_parameters(SimpleModel, weights, reuse=True)
    second_model, second = load_parameters(SimpleModel, weights, reuse=True)
    assert not mismatches(first, second)
    value = torch.ones(1, 4)
    torch.testing.assert_close(first_model.model(value), second_model.model(value))
