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


def buffer_reusing_iterator(weight_dict):
    buffer = None
    for name, tensor in weight_dict.items():
        if buffer is None or buffer.numel() < tensor.numel():
            buffer = torch.empty(tensor.numel(), dtype=tensor.dtype)
        view = buffer[: tensor.numel()].view(tensor.shape)
        view.copy_(tensor)
        yield name, view


def make_pooling_model():
    pooling_cls = _create_pooling_model_cls(SimpleModel)
    model = SimpleModel()
    model.__class__ = pooling_cls
    model.lm_head = StageMissingLayer("output", model.lm_head)
    return model


def simple_weights():
    torch.manual_seed(42)
    return {
        "model.embed.weight": torch.randn(8, 4),
        "model.layer0.weight": torch.randn(8, 8),
        "model.layer1.weight": torch.randn(8, 8),
        "model.norm.weight": torch.randn(4, 8),
        "lm_head.weight": torch.randn(16, 8),
    }


def run():
    weights = simple_weights()
    reference = SimpleModel()
    reference.load_weights(weights.items())
    candidate = make_pooling_model()
    for parameter in candidate.parameters():
        parameter.data.zero_()
    candidate.load_weights(buffer_reusing_iterator(weights))
    expected = {
        name: parameter.detach()
        for name, parameter in reference.named_parameters()
        if not name.startswith("lm_head")
    }
    actual = {name: parameter.detach() for name, parameter in candidate.named_parameters()}
    mismatched = [name for name in expected if not torch.equal(expected[name], actual[name])]
    sample = torch.tensor([[1.0, 2.0, 3.0, 4.0]])
    expected_output = reference.model(sample)
    actual_output = candidate.model(sample)
    return mismatched, torch.equal(expected_output, actual_output)
