from __future__ import annotations

import json

from verifier_support import PARSERS, argument, run_probe, wire


ENTITY_CASES = {
    "named": "&amp; &lt; &gt; &quot; &apos; &amp;amp;",
    "decimal": "&#38; &#60; &#62; &#34; &#39; &#00038; &#128512;",
    "hexadecimal": "&#x26; &#x3C; &#x3E; &#x22; &#x27; &#X3E; &#x1F600;",
}
STREAM_SCHEDULES = {
    "one-scalar": [],
    "whole-response": [1_000_000],
    "mixed-small": [1, 7, 2, 13, 3, 5] * 256,
    "entity-boundaries": [2, 1, 1, 3, 1, 4, 2, 1] * 256,
}


def main() -> int:
    results = []
    for parser in PARSERS:
        for entity_kind, entity_text in ENTITY_CASES.items():
            value = f"{parser}:{entity_kind}:{entity_text}"
            complete = run_probe(
                parser,
                "complete",
                wire(parser, [("content", value)]),
            )
            actual = argument(complete)["content"]
            results.append(
                {
                    "parser": parser,
                    "mode": "complete",
                    "schedule": "whole-response",
                    "entity_kind": entity_kind,
                    "preserved": actual == value,
                    "actual": actual,
                }
            )
            for schedule, sizes in STREAM_SCHEDULES.items():
                streamed = run_probe(
                    parser,
                    "stream",
                    wire(parser, [("content", value)]),
                    chunk_sizes=sizes,
                )
                actual = argument(streamed)["content"]
                results.append(
                    {
                        "parser": parser,
                        "mode": "stream",
                        "schedule": schedule,
                        "entity_kind": entity_kind,
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
    assert len(results) == 60, results
    assert all(result["preserved"] for result in results), results
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
