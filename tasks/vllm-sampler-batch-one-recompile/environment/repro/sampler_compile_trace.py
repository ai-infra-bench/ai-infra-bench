from __future__ import annotations

import json

from sampler_compile_fixture import run_compile_trace


def main() -> int:
    result = run_compile_trace((1, 2, 8, 3))
    result["entrypoint"] = "Sampler.gather_logprobs with real Torch Dynamo graph counting"
    result["single_graph"] = result["compile_counts"] == [1, 1, 1, 1]
    print(json.dumps(result, indent=2))
    return 0 if result["single_graph"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
