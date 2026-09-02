from __future__ import annotations

import json

from layerwise_fixture import run_late_bias


def main() -> int:
    observed = run_late_bias()
    result = {
        "entrypoint": "production initialize_online_processing and weight loaders",
        **observed,
        "waited_for_bias": observed["processed_after_weight"] == 0,
        "processed_loaded_bias": observed["bias_seen_after_bias"] == [3.0] * 4,
    }
    print(json.dumps(result, indent=2))
    return 0 if result["waited_for_bias"] and result["processed_loaded_bias"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
