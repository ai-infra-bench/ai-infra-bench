from __future__ import annotations

import pydantic
import pytest
from torch import nn

from vllm.config import ModelConfig
from vllm.config.load import LoadConfig
from vllm.model_executor.model_loader import (
    get_model_loader,
    register_model_loader,
)
from vllm.model_executor.model_loader.base_loader import BaseModelLoader


def default_loader(**kwargs):
    return get_model_loader(LoadConfig(**kwargs))


def test_non_string_load_formats_are_rejected_early() -> None:
    for value in (None, 123, ["safetensors"]):
        with pytest.raises(pydantic.ValidationError) as error:
            LoadConfig(load_format=value)
        assert "load_format" in str(error.value)


def test_unknown_safetensors_strategies_are_rejected() -> None:
    for value in ("prefecth", "stream", ""):
        with pytest.raises(pydantic.ValidationError) as error:
            LoadConfig(safetensors_load_strategy=value)
        assert "safetensors_load_strategy" in str(error.value)


def test_supported_safetensors_strategies_remain_valid() -> None:
    for value in (None, "lazy", "eager", "prefetch", "torchao"):
        config = LoadConfig(safetensors_load_strategy=value)
        assert config.safetensors_load_strategy == value


def test_extra_config_must_be_a_mapping() -> None:
    for value in (None, [], "threads"):
        with pytest.raises(ValueError, match="model_loader_extra_config"):
            default_loader(model_loader_extra_config=value)


def test_multithread_flag_must_be_boolean() -> None:
    for value in (1, 0, "true", []):
        with pytest.raises(ValueError, match="enable_multithread_load"):
            default_loader(
                model_loader_extra_config={"enable_multithread_load": value}
            )


def test_invalid_thread_counts_are_rejected_at_loader_construction() -> None:
    for value in (0, -1, 1.5, "8"):
        with pytest.raises(ValueError, match="num_threads"):
            default_loader(
                model_loader_extra_config={
                    "enable_multithread_load": True,
                    "num_threads": value,
                }
            )


def test_positive_thread_counts_remain_valid() -> None:
    for value in (1, 4, 32):
        loader = default_loader(
            model_loader_extra_config={
                "enable_multithread_load": True,
                "num_threads": value,
            }
        )
        assert loader is not None


def test_multithread_rejects_non_lazy_strategies() -> None:
    for strategy in ("eager", "prefetch", "torchao"):
        with pytest.raises(ValueError, match="safetensors_load_strategy"):
            default_loader(
                safetensors_load_strategy=strategy,
                model_loader_extra_config={"enable_multithread_load": True},
            )


def test_multithread_default_and_lazy_strategies_remain_valid() -> None:
    for strategy in (None, "lazy"):
        loader = default_loader(
            safetensors_load_strategy=strategy,
            model_loader_extra_config={"enable_multithread_load": True},
        )
        assert loader is not None


def test_custom_string_load_format_remains_extensible() -> None:
    name = "hidden_validation_loader"

    @register_model_loader(name)
    class HiddenValidationLoader(BaseModelLoader):
        def download_model(self, model_config: ModelConfig) -> None:
            pass

        def load_weights(self, model: nn.Module, model_config: ModelConfig) -> None:
            pass

    assert isinstance(
        get_model_loader(LoadConfig(load_format=name)),
        HiddenValidationLoader,
    )


def test_unknown_extra_keys_are_still_rejected() -> None:
    with pytest.raises(ValueError, match="Unexpected extra config keys"):
        default_loader(model_loader_extra_config={"not_a_loader_option": True})
