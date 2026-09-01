from __future__ import annotations

import json

import torch

from mrope_fixture import (
    ModelConfig,
    compute,
    image_feature,
    reference_positions,
    standard_image_prompt,
    video_feature,
)


def main() -> int:
    standard, image = standard_image_prompt([10], (1, 2, 2), [30, 31])
    changed = list(standard)
    start = image.mm_position.offset
    changed[start : start + image.mm_position.length] = [991] * 4

    standard_positions, standard_delta = compute(standard, [image])
    changed_positions, changed_delta = compute(changed, [image])
    expected, expected_delta = reference_positions(changed, [image])

    cfg = ModelConfig()
    video = video_feature(2, (2, 1, 2), seconds_per_grid=1.5)
    video_tokens = (
        [10, cfg.vision_start_token_id]
        + [cfg.video_token_id] * 4
        + [cfg.vision_end_token_id, 30]
    )
    video_positions, video_delta = compute(video_tokens, [video])
    video_expected, video_expected_delta = reference_positions(video_tokens, [video])
    sentinel_invariant = (
        torch.equal(standard_positions, expected)
        and torch.equal(changed_positions, expected)
        and standard_delta == changed_delta == expected_delta
    )
    video_matches_reference = (
        torch.equal(video_positions, video_expected)
        and video_delta == video_expected_delta
    )

    print(
        json.dumps(
            {
                "entrypoint": "PaddleOCRVLForConditionalGeneration.get_mrope_input_positions with real MultiModalFeatureSpec objects",
                "sentinel_invariant": sentinel_invariant,
                "image_shape": list(changed_positions.shape),
                "image_delta": changed_delta,
                "video_shape": list(video_positions.shape),
                "video_delta": video_delta,
                "video_matches_reference": video_matches_reference,
                "video_temporal_positions": video_positions[0, 2:6].tolist(),
            },
            separators=(",", ":"),
        )
    )
    assert sentinel_invariant
    assert video_matches_reference
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
