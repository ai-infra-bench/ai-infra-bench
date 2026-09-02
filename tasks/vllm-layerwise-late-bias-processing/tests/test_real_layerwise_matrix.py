from __future__ import annotations

import json

from layerwise_fixture import LateBiasLayer, finalize, load_bias, load_weight


def main() -> int:
    cases = []
    for bias_value in (3.0, -2.5):
        layer = LateBiasLayer(with_skip_buffer=True)
        load_weight(layer, bias_value + 1)
        after_weight = len(layer.quant_method.processed_biases)
        load_bias(layer, bias_value)
        cases.append(
            {
                "bias_value": bias_value,
                "processed_after_weight": after_weight,
                "processed_after_bias": len(layer.quant_method.processed_biases),
                "bias_seen": layer.quant_method.processed_biases[-1].tolist(),
            }
        )
        finalize(layer)
    report = {
        "entrypoint": "real layerwise online-processing loader lifecycle",
        "cases": cases,
        "all_waited": all(case["processed_after_weight"] == 0 for case in cases),
        "all_processed_once": all(case["processed_after_bias"] == 1 for case in cases),
    }
    print(json.dumps(report, separators=(",", ":")))
    assert report["all_waited"] and report["all_processed_once"]
    assert cases[0]["bias_seen"] == [3.0] * 4
    assert cases[1]["bias_seen"] == [-2.5] * 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
