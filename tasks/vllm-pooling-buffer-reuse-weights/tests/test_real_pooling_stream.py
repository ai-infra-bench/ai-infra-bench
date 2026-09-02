from __future__ import annotations

import json

import torch

from pooling_fixture import SimpleModel, load_parameters, mismatches, simple_weights


def main() -> int:
    weights = simple_weights()
    reference, expected = load_parameters(SimpleModel, weights, reuse=False)
    candidate, actual = load_parameters(SimpleModel, weights, reuse=True)
    bad = mismatches(actual, expected)
    value = torch.tensor([[1.0, -2.0, 3.0, -4.0]])
    output_matches = torch.equal(reference.model(value), candidate.model(value))
    print(
        json.dumps(
            {
                "entrypoint": "production pooling model adapter and one-shot checkpoint iterator",
                "mismatched_parameters": bad,
                "output_matches_reference": output_matches,
            },
            separators=(",", ":"),
        )
    )
    assert not bad
    assert output_matches
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
