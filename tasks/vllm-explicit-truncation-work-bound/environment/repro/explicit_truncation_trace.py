from __future__ import annotations

import json

from renderer_fixture import build_renderer, tokenize


def main() -> int:
    renderer = build_renderer(max_chars_per_token=1)
    result = tokenize(
        renderer,
        "0123456789" * 50,
        max_total_tokens=100,
        truncate_prompt_tokens=4,
        truncation_side="left",
    )[0]
    observed = renderer.tokenizer.calls[-1]
    report = {
        "entrypoint": "HfRenderer render and tokenize prompt pipeline",
        "input_characters": 500,
        "tokenizer_input_characters": len(observed["text"]),
        "returned_token_count": len(result["prompt_token_ids"]),
        "returned_from_requested_side": observed["text"].endswith("6789"),
        "work_bounded": len(observed["text"]) <= 100,
    }
    print(json.dumps(report, indent=2))
    return 0 if report["work_bounded"] and report["returned_token_count"] == 4 else 3


if __name__ == "__main__":
    raise SystemExit(main())
