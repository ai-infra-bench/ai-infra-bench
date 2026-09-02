from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import torch

from vllm.config import ModelConfig
from vllm.inputs import SingletonPrompt
from vllm.renderers import TokenizeParams
from vllm.renderers.hf import HfRenderer
from vllm.renderers.inputs.preprocess import parse_model_prompt, prompt_to_seq


@dataclass
class MockHFConfig:
    model_type: str = "any"


@dataclass
class MockModelConfig:
    runner_type = "generate"
    model: str = "local-reduction"
    tokenizer: str = "local-reduction"
    trust_remote_code: bool = False
    tokenizer_revision = None
    tokenizer_mode = "auto"
    hf_config = MockHFConfig()
    encoder_config: dict[str, Any] | None = None
    enable_prompt_embeds: bool = True
    skip_tokenizer_init: bool = False
    is_encoder_decoder: bool = False
    is_multimodal_model: bool = False
    renderer_num_workers: int = 1
    hidden_size: int = 16
    dtype: torch.dtype = torch.float32

    def get_hidden_size(self) -> int:
        return self.hidden_size


@dataclass
class MockParallelConfig:
    _api_process_rank: int = 0


@dataclass
class MockVllmConfig:
    model_config: MockModelConfig
    parallel_config: MockParallelConfig


@dataclass
class RecordingTokenizer:
    truncation_side: str = "left"
    max_chars_per_token: int = 1

    def __post_init__(self) -> None:
        self.calls: list[dict] = []

    def decode(self, tokens: list[int]):
        return str(tokens)

    def encode(self, text: str, **kwargs):
        self.calls.append({"text": text, "kwargs": dict(kwargs)})
        values = list(range(len(text)))
        if kwargs.get("truncation") and kwargs.get("max_length") is not None:
            limit = kwargs["max_length"]
            values = values[-limit:] if self.truncation_side == "left" else values[:limit]
        return values

    def __call__(self, text: str, **kwargs):
        return {"input_ids": self.encode(text, **kwargs)}


def build_renderer(*, tokenizer_side: str = "left", max_chars_per_token: int = 1):
    config = MockModelConfig()
    tokenizer = RecordingTokenizer(tokenizer_side, max_chars_per_token)
    return HfRenderer(
        MockVllmConfig(config, MockParallelConfig()),
        tokenizer=tokenizer,
    )


def preprocess(
    renderer: HfRenderer,
    prompt: SingletonPrompt | bytes | Sequence[SingletonPrompt | bytes],
):
    return [
        item if isinstance(item, bytes) else parse_model_prompt(renderer.model_config, item)
        for item in prompt_to_seq(prompt)
    ]


def tokenize(renderer: HfRenderer, text, **params):
    prompts = renderer.render_prompts(preprocess(renderer, text))
    return renderer.tokenize_prompts(prompts, TokenizeParams(**params))
