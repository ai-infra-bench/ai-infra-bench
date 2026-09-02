from __future__ import annotations

from collections.abc import Iterable

import torch

from vllm.model_executor.models.adapters import _create_pooling_model_cls
from vllm.model_executor.models.utils import AutoWeightsLoader, StageMissingLayer


class SimpleInnerModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.embed = torch.nn.Linear(4, 8, bias=False)
        self.layer0 = torch.nn.Linear(8, 8, bias=False)
        self.layer1 = torch.nn.Linear(8, 8, bias=False)
        self.norm = torch.nn.Linear(8, 4, bias=False)

    def forward(self, value):
        return self.norm(self.layer1(self.layer0(self.embed(value))))

    def load_weights(self, weights):
        params = dict(self.named_parameters())
        loaded = set()
        for name, tensor in weights:
            if name in params:
                params[name].data.copy_(tensor)
                loaded.add(name)
        return loaded


class SimpleModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.model = SimpleInnerModel()
        self.lm_head = torch.nn.Linear(8, 16, bias=False)

    def load_weights(self, weights):
        return AutoWeightsLoader(self).load_weights(weights)


class PackedWeightInnerModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.qkv_proj = torch.nn.Linear(4, 16, bias=False)
        self.out = torch.nn.Linear(8, 4, bias=False)

    def load_weights(self, weights):
        params = dict(self.named_parameters())
        loaded = set()
        for name, tensor in weights:
            if name == "q_proj.weight":
                params["qkv_proj.weight"].data[:8].copy_(tensor)
                loaded.add("qkv_proj.weight")
            elif name == "k_proj.weight":
                params["qkv_proj.weight"].data[8:].copy_(tensor)
                loaded.add("qkv_proj.weight")
            elif name in params:
                params[name].data.copy_(tensor)
                loaded.add(name)
        return loaded


class PackedWeightModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.model = PackedWeightInnerModel()
        self.lm_head = torch.nn.Linear(4, 8, bias=False)

    def load_weights(self, weights):
        return AutoWeightsLoader(self).load_weights(weights)


class ConsumptionModel(SimpleModel):
    first_consumed_count: int | None = None
    yielded_count = 0

    def load_weights(self, weights):
        params = dict(self.named_parameters())
        for name, tensor in weights:
            if self.first_consumed_count is None:
                self.first_consumed_count = self.yielded_count
            if name in params:
                params[name].data.copy_(tensor)
        return set(params)


def buffer_reusing_iterator(weight_dict, model=None):
    buffer = None
    for name, tensor in weight_dict.items():
        if buffer is None or buffer.numel() < tensor.numel():
            buffer = torch.empty(tensor.numel(), dtype=tensor.dtype)
        view = buffer[: tensor.numel()].view(tensor.shape)
        view.copy_(tensor)
        if model is not None:
            model.yielded_count += 1
        yield name, view


def make_pooling_model(base_cls=SimpleModel):
    pooling_cls = _create_pooling_model_cls(base_cls)
    model = base_cls()
    model.__class__ = pooling_cls
    model.lm_head = StageMissingLayer("output", model.lm_head)
    return model


def simple_weights(prefix: str = "model."):
    torch.manual_seed(42)
    return {
        f"{prefix}embed.weight": torch.randn(8, 4),
        f"{prefix}layer0.weight": torch.randn(8, 8),
        f"{prefix}layer1.weight": torch.randn(8, 8),
        f"{prefix}norm.weight": torch.randn(4, 8),
        "lm_head.weight": torch.randn(16, 8),
    }


def packed_weights():
    torch.manual_seed(43)
    return {
        "model.q_proj.weight": torch.randn(8, 4),
        "model.k_proj.weight": torch.randn(8, 4),
        "model.out.weight": torch.randn(4, 8),
        "lm_head.weight": torch.randn(8, 4),
    }


def expected_parameters(base_cls, weights):
    model = base_cls()
    inner_weights = (
        (name.removeprefix("model."), tensor)
        for name, tensor in weights.items()
        if name != "lm_head.weight"
    )
    model.model.load_weights(inner_weights)
    return {
        f"model.{name}": parameter.detach().clone()
        for name, parameter in model.model.named_parameters()
    }


def load_parameters(base_cls, weights, *, reuse: bool):
    model = make_pooling_model(base_cls)
    for parameter in model.parameters():
        parameter.data.zero_()
    iterator: Iterable = buffer_reusing_iterator(weights) if reuse else iter(weights.items())
    model.load_weights(iterator)
    return model, {name: parameter.detach().clone() for name, parameter in model.named_parameters()}


def mismatches(actual: dict, expected: dict) -> list[str]:
    return [name for name in expected if not torch.equal(actual[name], expected[name])]
