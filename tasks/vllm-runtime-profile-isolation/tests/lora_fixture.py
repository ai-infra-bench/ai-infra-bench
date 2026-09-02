from __future__ import annotations

import tempfile
from collections import OrderedDict
from unittest.mock import MagicMock

import torch
import torch.nn as nn

from vllm.config import VllmConfig, set_current_vllm_config
from vllm.config.lora import LoRAConfig
from vllm.distributed import init_distributed_environment, initialize_model_parallel
from vllm.lora.layers import LoRAMapping
from vllm.lora.lora_model import LoRAModel
from vllm.lora.lora_weights import LoRALayerWeights
from vllm.lora.model_manager import (
    DEFAULT_LANGUAGE_WRAPPER_KEY,
    LRUCacheLoRAModelManager,
)
from vllm.model_executor.layers.linear import ColumnParallelLinear
from vllm.model_executor.models.interfaces import SupportsLoRA


class DummyLoRAModel(nn.Sequential, SupportsLoRA):
    pass


def _ensure_distributed() -> None:
    if torch.distributed.is_initialized():
        return
    rendezvous = tempfile.mkstemp(prefix="lora-routing-dist-")[1]
    init_distributed_environment(
        world_size=1,
        rank=0,
        distributed_init_method=f"file://{rendezvous}",
        local_rank=0,
        backend="gloo",
    )
    initialize_model_parallel(1, 1)


def _model() -> DummyLoRAModel:
    model = DummyLoRAModel(
        OrderedDict(
            [
                ("dense1", ColumnParallelLinear(16, 8, bias=False)),
                ("dense2", ColumnParallelLinear(8, 4, bias=False)),
            ]
        )
    )
    model.config = MagicMock()
    model.embedding_modules = {}
    model.packed_modules_mapping = {}
    return model


def _adapter(adapter_id: int, model: nn.Module) -> LoRAModel:
    loras = {}
    for name in ("dense1", "dense2"):
        weight = model.get_submodule(name).weight
        loras[name] = LoRALayerWeights(
            name,
            2,
            4,
            torch.full((2, weight.shape[1]), float(adapter_id)),
            torch.full((weight.shape[0], 2), float(adapter_id)),
        )
    return LoRAModel(adapter_id, 2, loras)


def make_manager(adapter_ids: tuple[int, ...] = (1, 2, 3, 4)):
    config = VllmConfig()
    with set_current_vllm_config(config):
        _ensure_distributed()
        model = _model()
        adapters = {adapter_id: _adapter(adapter_id, model) for adapter_id in adapter_ids}
        manager = LRUCacheLoRAModelManager(
            model=model,
            max_num_seqs=4,
            max_num_batched_tokens=16,
            vocab_size=128,
            lora_config=LoRAConfig(
                max_lora_rank=8,
                max_cpu_loras=max(4, len(adapter_ids)),
                max_loras=2,
                lora_dtype=torch.float32,
            ),
            device=torch.device("cpu"),
            vllm_config=config,
        )
    for adapter in adapters.values():
        assert manager.add_adapter(adapter)
    return manager


def route(manager, requested: tuple[int, ...]) -> dict:
    mapping = LoRAMapping(requested, requested)
    manager.set_adapter_mapping(mapping)
    wrapper = manager.punica_wrapper_mapping[DEFAULT_LANGUAGE_WRAPPER_KEY]
    indices = [int(value) for value in wrapper.token_lora_indices.tolist()]
    slots = list(manager.lora_index_to_id)
    resolved = [slots[index] if index >= 0 else 0 for index in indices]
    return {
        "requested": list(requested),
        "slots": slots,
        "indices": indices,
        "resolved": resolved,
    }


def activate(manager, *adapter_ids: int) -> None:
    for adapter_id in adapter_ids:
        assert manager.activate_adapter(adapter_id)


def swap_live_slots(manager) -> tuple[dict, dict]:
    activate(manager, 1, 2)
    before = route(manager, (1, 2))
    activate(manager, 3, 1, 2)
    after = route(manager, (1, 2))
    return before, after
