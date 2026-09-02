from __future__ import annotations

import asyncio

import pytest

from renderer_fixture import build_renderer, preprocess, tokenize
from vllm.renderers import TokenizeParams


def test_left_truncation_bounds_tokenizer_input_and_keeps_suffix() -> None:
    renderer = build_renderer(max_chars_per_token=1)
    result = tokenize(renderer, "A" * 180 + "RIGHT", max_total_tokens=40, truncate_prompt_tokens=5, truncation_side="left")[0]
    observed = renderer.tokenizer.calls[-1]["text"]
    assert len(observed) == 40 and observed.endswith("RIGHT")
    assert len(result["prompt_token_ids"]) == 5


def test_right_truncation_bounds_tokenizer_input_and_keeps_prefix() -> None:
    renderer = build_renderer(max_chars_per_token=1)
    result = tokenize(renderer, "LEFT" + "Z" * 180, max_total_tokens=40, truncate_prompt_tokens=5, truncation_side="right")[0]
    observed = renderer.tokenizer.calls[-1]["text"]
    assert len(observed) == 40 and observed.startswith("LEFT")
    assert len(result["prompt_token_ids"]) == 5


def test_character_bound_respects_tokenizer_ratio() -> None:
    renderer = build_renderer(max_chars_per_token=4)
    tokenize(renderer, "x" * 1000, max_total_tokens=30, max_output_tokens=5, truncate_prompt_tokens=7, truncation_side="left")
    assert len(renderer.tokenizer.calls[-1]["text"]) == 100


def test_async_renderer_uses_same_bounded_input() -> None:
    renderer = build_renderer(max_chars_per_token=2)
    prompts = renderer.render_prompts(preprocess(renderer, "x" * 500))
    result = asyncio.run(renderer.tokenize_prompts_async(prompts, TokenizeParams(max_total_tokens=60, truncate_prompt_tokens=9, truncation_side="right")))
    assert len(renderer.tokenizer.calls[-1]["text"]) == 120
    assert len(result[0]["prompt_token_ids"]) == 9


def test_no_truncation_still_rejects_oversized_text() -> None:
    renderer = build_renderer(max_chars_per_token=1)
    with pytest.raises(ValueError, match="maximum context length"):
        tokenize(renderer, "x" * 51, max_total_tokens=50)
    assert renderer.tokenizer.calls == []


def test_tokenizer_default_truncation_retains_existing_bound() -> None:
    renderer = build_renderer(tokenizer_side="left", max_chars_per_token=2)
    result = tokenize(renderer, "x" * 150, max_total_tokens=50, truncate_prompt_tokens=8, truncation_side=None)[0]
    call = renderer.tokenizer.calls[-1]
    assert len(call["text"]) == 150
    assert call["kwargs"]["truncation"] is True
    assert call["kwargs"]["max_length"] == 8
    assert len(result["prompt_token_ids"]) == 8


def test_without_context_limit_does_not_invent_a_bound() -> None:
    renderer = build_renderer(max_chars_per_token=1)
    tokenize(renderer, "x" * 211, max_total_tokens=None, truncate_prompt_tokens=6, truncation_side="left")
    assert len(renderer.tokenizer.calls[-1]["text"]) == 211


def test_token_list_input_is_unchanged() -> None:
    renderer = build_renderer()
    result = tokenize(renderer, list(range(20)), max_total_tokens=50, truncate_prompt_tokens=4, truncation_side="left")[0]
    assert result["prompt_token_ids"] == [16, 17, 18, 19]
    assert renderer.tokenizer.calls == []


def test_lowercase_and_special_token_options_remain_active() -> None:
    renderer = build_renderer(max_chars_per_token=1)
    tokenize(renderer, "ABC" * 40, max_total_tokens=20, truncate_prompt_tokens=4, truncation_side="right", do_lower_case=True, add_special_tokens=False)
    call = renderer.tokenizer.calls[-1]
    assert call["text"] == ("abc" * 7)[:20]
    assert call["kwargs"]["add_special_tokens"] is False
