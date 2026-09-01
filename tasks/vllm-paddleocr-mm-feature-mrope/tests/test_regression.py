from __future__ import annotations

import time

import torch

from mrope_fixture import (
    ModelConfig,
    compute,
    image_feature,
    reference_positions,
    standard_image_prompt,
    video_feature,
)


def assert_reference(tokens: list[int], features) -> tuple[torch.Tensor, int]:
    actual, delta = compute(tokens, features)
    expected, expected_delta = reference_positions(tokens, features)
    assert torch.equal(actual, expected)
    assert delta == expected_delta
    return actual, delta


def test_text_only_positions_remain_linear() -> None:
    tokens = [11, 12, 13, 14, 15]
    positions, delta = assert_reference(tokens, [])
    assert torch.equal(positions, torch.arange(5).expand(3, 5))
    assert delta == 0


def test_standard_single_image_positions_are_preserved() -> None:
    tokens, feature = standard_image_prompt([10], (1, 2, 2), [30, 31])
    positions, _ = assert_reference(tokens, [feature])
    assert positions.shape == (3, len(tokens))


def test_image_at_prompt_start_is_preserved() -> None:
    tokens, feature = standard_image_prompt([], (1, 2, 2), [10, 11])
    assert feature.mm_position.offset == 1
    assert_reference(tokens, [feature])


def test_video_temporal_scaling_is_preserved() -> None:
    cfg = ModelConfig()
    grid = (2, 1, 2)
    offset = 2
    feature = video_feature(offset, grid, seconds_per_grid=1.5)
    tokens = (
        [10, cfg.vision_start_token_id]
        + [cfg.video_token_id] * 4
        + [cfg.vision_end_token_id, 30]
    )
    positions, _ = assert_reference(tokens, [feature])
    assert positions[0, offset : offset + 4].tolist() == [2, 2, 5, 5]


def test_mixed_image_video_features_may_be_unordered() -> None:
    cfg = ModelConfig()
    image = image_feature(2, (1, 1, 2), identifier="page")
    video_offset = 2 + 2 + 1 + 2 + 1
    video = video_feature(
        video_offset,
        (2, 1, 1),
        seconds_per_grid=0.5,
        identifier="clip",
    )
    tokens = (
        [10, cfg.vision_start_token_id]
        + [cfg.image_token_id] * 2
        + [cfg.vision_end_token_id, 20, 21, cfg.vision_start_token_id]
        + [cfg.video_token_id] * 2
        + [cfg.vision_end_token_id, 30]
    )
    assert_reference(tokens, [video, image])


def test_feature_offset_is_authoritative_without_sentinel_tokens() -> None:
    tokens, feature = standard_image_prompt([10], (1, 2, 2), [30, 31])
    offset = feature.mm_position.offset
    tokens[offset : offset + feature.mm_position.length] = [777] * 4
    assert_reference(tokens, [feature])


def test_same_feature_metadata_is_invariant_to_placeholder_ids() -> None:
    standard, feature = standard_image_prompt([10, 11], (1, 2, 3), [30])
    changed = list(standard)
    start = feature.mm_position.offset
    changed[start : start + feature.mm_position.length] = [888] * 6
    standard_positions, standard_delta = compute(standard, [feature])
    changed_positions, changed_delta = compute(changed, [feature])
    assert torch.equal(standard_positions, changed_positions)
    assert standard_delta == changed_delta


def test_multiple_images_are_sorted_by_feature_offset() -> None:
    cfg = ModelConfig()
    first = image_feature(2, (1, 1, 2), identifier="first")
    second_offset = 2 + 2 + 1 + 3 + 1
    second = image_feature(second_offset, (1, 2, 1), identifier="second")
    tokens = (
        [10, cfg.vision_start_token_id]
        + [cfg.image_token_id] * 2
        + [cfg.vision_end_token_id, 20, 21, 22, cfg.vision_start_token_id]
        + [cfg.image_token_id] * 2
        + [cfg.vision_end_token_id, 30]
    )
    assert_reference(tokens, [second, first])


def test_long_prompt_uses_feature_offset_and_completes_promptly() -> None:
    tokens = [7] * 120_000
    feature = image_feature(60_000, (1, 2, 2))
    started = time.perf_counter()
    positions, _ = assert_reference(tokens, [feature])
    elapsed = time.perf_counter() - started
    assert positions.shape == (3, len(tokens))
    assert elapsed < 5.0


def test_public_return_contract_is_cpu_int64_tensor() -> None:
    tokens, feature = standard_image_prompt([10], (1, 1, 3), [20])
    positions, delta = assert_reference(tokens, [feature])
    assert isinstance(positions, torch.Tensor)
    assert positions.device.type == "cpu"
    assert positions.dtype == torch.int64
    assert positions.shape == (3, len(tokens))
    assert isinstance(delta, int)
