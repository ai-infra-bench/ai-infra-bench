from __future__ import annotations

import json

from sampler_compile_fixture import run_compile_trace


def main() -> int:
    sequences = ((1, 3, 7, 2), (5, 1, 4), (1, 1, 6))
    cases = []
    for sequence in sequences:
        result = run_compile_trace(sequence, vocab_size=29)
        cases.append(
            {
                "batch_sizes": result["batch_sizes"],
                "compile_counts": result["compile_counts"],
                "rank_lengths": [len(output.selected_token_ranks) for output in result["outputs"]],
            }
        )
    report = {
        "entrypoint": "real Sampler.gather_logprobs and Torch Dynamo compile backend",
        "cases": cases,
        "all_single_graph": all(set(case["compile_counts"]) == {1} for case in cases),
    }
    print(json.dumps(report, separators=(",", ":")))
    assert report["all_single_graph"]
    for case in cases:
        assert case["rank_lengths"] == case["batch_sizes"]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
