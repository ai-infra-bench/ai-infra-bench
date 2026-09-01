from __future__ import annotations

import json
import time

import torch

from mrope_fixture import compute, reference_positions, standard_image_prompt


def main() -> int:
    standard, feature = standard_image_prompt([10], (1, 2, 2), [30, 31])
    mutated = list(standard)
    start = feature.mm_position.offset
    mutated[start : start + feature.mm_position.length] = [777] * feature.mm_position.length

    expected, expected_delta = reference_positions(mutated, [feature])
    standard_positions, standard_delta = compute(standard, [feature])
    started = time.perf_counter()
    mutated_positions, mutated_delta = compute(mutated, [feature])
    elapsed = time.perf_counter() - started

    result = {
        "feature_offset": feature.mm_position.offset,
        "feature_length": feature.mm_position.length,
        "standard_matches_reference": torch.equal(standard_positions, expected),
        "standard_delta": standard_delta,
        "mutated_matches_reference": torch.equal(mutated_positions, expected),
        "mutated_delta": mutated_delta,
        "expected_delta": expected_delta,
        "mismatched_coordinates": int((mutated_positions != expected).sum().item()),
        "elapsed_seconds": elapsed,
    }
    print(json.dumps(result, indent=2))
    passed = result["mutated_matches_reference"] and mutated_delta == expected_delta
    print(f"mm_feature_position_contract={passed}")
    return 0 if passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
