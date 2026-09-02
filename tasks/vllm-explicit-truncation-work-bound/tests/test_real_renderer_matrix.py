from __future__ import annotations

import asyncio
import json

from renderer_fixture import build_renderer, preprocess, tokenize
from vllm.renderers import TokenizeParams


def main() -> int:
    left = build_renderer(max_chars_per_token=3)
    left_result = tokenize(left, "α" * 503 + "끝", max_total_tokens=70, max_output_tokens=10, truncate_prompt_tokens=11, truncation_side="left")[0]
    right = build_renderer(max_chars_per_token=2)
    prompts = right.render_prompts(preprocess(right, "START" + "β" * 600))
    right_result = asyncio.run(right.tokenize_prompts_async(prompts, TokenizeParams(max_total_tokens=80, max_output_tokens=8, truncate_prompt_tokens=13, truncation_side="right")))[0]
    report = {
        "entrypoint": "real HfRenderer sync and async prompt pipeline",
        "left_tokenizer_chars": len(left.tokenizer.calls[-1]["text"]),
        "right_tokenizer_chars": len(right.tokenizer.calls[-1]["text"]),
        "left_tokens": len(left_result["prompt_token_ids"]),
        "right_tokens": len(right_result["prompt_token_ids"]),
        "left_suffix_preserved": left.tokenizer.calls[-1]["text"].endswith("끝"),
        "right_prefix_preserved": right.tokenizer.calls[-1]["text"].startswith("START"),
    }
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    assert report == {
        "entrypoint": "real HfRenderer sync and async prompt pipeline",
        "left_tokenizer_chars": 180,
        "right_tokenizer_chars": 144,
        "left_tokens": 11,
        "right_tokens": 13,
        "left_suffix_preserved": True,
        "right_prefix_preserved": True,
    }
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
