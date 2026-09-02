from __future__ import annotations

import torch

from vllm.model_executor.layers.quantization.base_config import QuantizeMethodBase
from vllm.model_executor.model_loader.reload.layerwise import (
    finalize_layerwise_processing,
    initialize_online_processing,
)
from vllm.model_executor.model_loader.weight_utils import default_weight_loader


class RecordingQuantMethod(QuantizeMethodBase):
    uses_meta_device = True

    def __init__(self) -> None:
        self.processed_biases: list[torch.Tensor | None] = []
        self.processed_weights: list[torch.Tensor] = []

    def create_weights(self, layer, *args, **kwargs) -> None:
        return None

    def apply(self, layer, *args, **kwargs):
        raise NotImplementedError

    def process_weights_after_loading(self, layer) -> None:
        bias = getattr(layer, "bias", None)
        self.processed_biases.append(None if bias is None else bias.detach().clone())
        self.processed_weights.append(layer.weight.detach().clone())


class LateBiasLayer(torch.nn.Module):
    def __init__(self, *, with_bias: bool = True, with_skip_buffer: bool = False):
        super().__init__()
        self.quant_method = RecordingQuantMethod()
        weight = torch.nn.Parameter(torch.empty(4, 2, device="meta"))
        weight.weight_loader = default_weight_loader
        self.register_parameter("weight", weight)
        initialize_online_processing(self)
        if with_bias:
            bias = torch.nn.Parameter(torch.zeros(4))
            bias.weight_loader = default_weight_loader
            self.register_parameter("bias", bias)
        if with_skip_buffer:
            self.register_buffer("_expert_map", torch.arange(4), persistent=False)


def load_weight(layer: LateBiasLayer, value: float = 2.0) -> None:
    layer.weight.weight_loader(layer.weight, torch.full((4, 2), value))


def load_bias(layer: LateBiasLayer, value: float = 3.0) -> None:
    layer.bias.weight_loader(layer.bias, torch.full((4,), value))


def run_late_bias(value: float = 3.0) -> dict:
    layer = LateBiasLayer()
    load_weight(layer)
    after_weight = len(layer.quant_method.processed_biases)
    bias_seen_after_weight = None if not layer.quant_method.processed_biases else layer.quant_method.processed_biases[-1].tolist()
    load_bias(layer, value)
    return {
        "layer": layer,
        "processed_after_weight": after_weight,
        "bias_seen_after_weight": bias_seen_after_weight,
        "processed_after_bias": len(layer.quant_method.processed_biases),
        "bias_seen_after_bias": layer.quant_method.processed_biases[-1].tolist(),
        "final_bias": layer.bias.detach().tolist(),
    }


def finalize(layer: LateBiasLayer) -> None:
    finalize_layerwise_processing(layer, model_config=None)  # type: ignore[arg-type]
