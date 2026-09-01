from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import torch

from vllm.model_executor.models.paddleocr_vl import (
    PaddleOCRVLForConditionalGeneration,
)
from vllm.multimodal.inputs import (
    MultiModalFeatureSpec,
    MultiModalFieldElem,
    MultiModalKwargsItem,
    PlaceholderRange,
)


@dataclass
class VisionConfig:
    spatial_merge_size: int = 2
    patch_size: int = 14
    tokens_per_second: float = 2.0


@dataclass
class ModelConfig:
    image_token_id: int = 151655
    video_token_id: int = 151654
    vision_start_token_id: int = 151652
    vision_end_token_id: int = 151653
    vision_config: VisionConfig = field(default_factory=VisionConfig)


def make_model():
    model = object.__new__(PaddleOCRVLForConditionalGeneration)
    model.config = ModelConfig()
    return model


def _field(value) -> MultiModalFieldElem:
    return MultiModalFieldElem(data=torch.as_tensor(value), field=None)


def image_feature(
    offset: int,
    grid: tuple[int, int, int],
    *,
    identifier: str = "image",
) -> MultiModalFeatureSpec:
    t, h, w = grid
    merge = 2
    length = t * h * w
    return MultiModalFeatureSpec(
        data=MultiModalKwargsItem(
            {"image_grid_thw": _field((t, h * merge, w * merge))}
        ),
        modality="image",
        identifier=identifier,
        mm_position=PlaceholderRange(offset=offset, length=length),
    )


def video_feature(
    offset: int,
    grid: tuple[int, int, int],
    *,
    seconds_per_grid: float,
    identifier: str = "video",
) -> MultiModalFeatureSpec:
    t, h, w = grid
    merge = 2
    length = t * h * w
    return MultiModalFeatureSpec(
        data=MultiModalKwargsItem(
            {
                "video_grid_thw": _field((t, h * merge, w * merge)),
                "second_per_grid_ts": _field(seconds_per_grid),
            }
        ),
        modality="video",
        identifier=identifier,
        mm_position=PlaceholderRange(offset=offset, length=length),
    )


def reference_positions(
    input_tokens: list[int],
    features: list[MultiModalFeatureSpec],
    *,
    tokens_per_second: float = 2.0,
) -> tuple[torch.Tensor, int]:
    parts: list[np.ndarray] = []
    cursor = 0
    current_max = -1
    for feature in sorted(features, key=lambda item: item.mm_position.offset):
        offset = feature.mm_position.offset
        text_len = offset - cursor
        start = current_max + 1
        if text_len:
            text = np.broadcast_to(np.arange(text_len), (3, text_len)) + start
            parts.append(text)
            current_max = int(text.max())

        assert feature.data is not None
        if feature.modality == "image":
            t, raw_h, raw_w = feature.data["image_grid_thw"].data.tolist()
            factor = 1.0
        else:
            t, raw_h, raw_w = feature.data["video_grid_thw"].data.tolist()
            factor = float(feature.data["second_per_grid_ts"].data.item())
            factor *= tokens_per_second
        h, w = raw_h // 2, raw_w // 2
        grid = np.indices((t, h, w))
        if factor != 1.0:
            grid[0] = (grid[0] * factor).astype(np.int64)
        vision = grid.reshape(3, -1) + text_len + start
        parts.append(vision)
        current_max = max(current_max, int(vision.max()))
        cursor = offset + t * h * w

    if cursor < len(input_tokens):
        text_len = len(input_tokens) - cursor
        start = current_max + 1
        tail = np.broadcast_to(np.arange(text_len), (3, text_len)) + start
        parts.append(tail)
    positions = np.concatenate(parts, axis=1).reshape(3, -1)
    delta = int(positions.max() + 1 - len(input_tokens))
    return torch.from_numpy(positions), delta


def standard_image_prompt(
    prefix: list[int],
    grid: tuple[int, int, int],
    suffix: list[int],
) -> tuple[list[int], MultiModalFeatureSpec]:
    model_config = ModelConfig()
    count = int(np.prod(grid))
    offset = len(prefix) + 1
    tokens = (
        prefix
        + [model_config.vision_start_token_id]
        + [model_config.image_token_id] * count
        + [model_config.vision_end_token_id]
        + suffix
    )
    return tokens, image_feature(offset, grid)


def compute(input_tokens: list[int], features: list[MultiModalFeatureSpec]):
    model = make_model()
    return model.get_mrope_input_positions(input_tokens, features)
