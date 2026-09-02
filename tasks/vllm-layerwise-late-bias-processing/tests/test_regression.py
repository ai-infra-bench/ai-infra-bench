from __future__ import annotations

import torch

from layerwise_fixture import LateBiasLayer, finalize, load_bias, load_weight, run_late_bias
from vllm.model_executor.model_loader.reload.meta import capture_layer_to_meta


def test_late_bias_waits_until_bias_load() -> None:
    observed = run_late_bias()
    assert observed["processed_after_weight"] == 0
    assert observed["processed_after_bias"] == 1


def test_processing_observes_loaded_bias_value() -> None:
    observed = run_late_bias(7.0)
    assert observed["bias_seen_after_bias"] == [7.0] * 4
    assert observed["final_bias"] == [7.0] * 4


def test_loaded_weight_and_bias_are_both_visible_at_processing() -> None:
    observed = run_late_bias(5.0)
    layer = observed["layer"]
    torch.testing.assert_close(layer.quant_method.processed_weights[-1], torch.full((4, 2), 2.0))
    torch.testing.assert_close(layer.quant_method.processed_biases[-1], torch.full((4,), 5.0))


def test_two_layers_track_late_bias_independently() -> None:
    first, second = LateBiasLayer(), LateBiasLayer()
    load_weight(first, 1.0)
    load_weight(second, 2.0)
    assert not first.quant_method.processed_biases
    assert not second.quant_method.processed_biases
    load_bias(second, 9.0)
    load_bias(first, 8.0)
    assert second.quant_method.processed_biases[-1].tolist() == [9.0] * 4
    assert first.quant_method.processed_biases[-1].tolist() == [8.0] * 4


def test_layer_without_bias_processes_after_weight() -> None:
    layer = LateBiasLayer(with_bias=False)
    load_weight(layer, 4.0)
    assert len(layer.quant_method.processed_biases) == 1
    assert layer.quant_method.processed_biases[0] is None


def test_never_loaded_skip_buffer_does_not_block_processing() -> None:
    layer = LateBiasLayer(with_skip_buffer=True)
    load_weight(layer)
    load_bias(layer)
    assert len(layer.quant_method.processed_biases) == 1


def test_bias_remains_outside_meta_capture() -> None:
    layer = torch.nn.Linear(2, 4, bias=True)
    captured_params, _ = capture_layer_to_meta(layer)
    assert "weight" in captured_params
    assert "bias" not in captured_params
    assert not layer.bias.is_meta


def test_missing_bias_defers_until_finalize() -> None:
    layer = LateBiasLayer()
    load_weight(layer)
    assert not layer.quant_method.processed_biases
    finalize(layer)
    assert len(layer.quant_method.processed_biases) == 1
    assert layer.quant_method.processed_biases[0].tolist() == [0.0] * 4


def test_processing_runs_exactly_once_after_complete_load() -> None:
    layer = LateBiasLayer()
    load_weight(layer)
    load_bias(layer)
    finalize(layer)
    assert len(layer.quant_method.processed_biases) == 1
