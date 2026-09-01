from __future__ import annotations

import json

from verifier_support import PARSERS, argument, run_probe, wire


def main() -> int:
    results = []
    for parser in PARSERS:
        for mode in ("complete", "stream"):
            value = f"{parser} &amp; &lt;literal&gt;"
            output = run_probe(
                parser,
                mode,
                wire(parser, [("content", value)]),
            )
            actual = argument(output)["content"]
            results.append(
                {
                    "parser": parser,
                    "mode": mode,
                    "preserved": actual == value,
                    "actual": actual,
                }
            )
    print(
        json.dumps(
            {
                "entrypoint": "compiled vllm-tool-parser crate",
                "cases": results,
            },
            separators=(",", ":"),
        )
    )
    assert all(result["preserved"] for result in results), results
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
