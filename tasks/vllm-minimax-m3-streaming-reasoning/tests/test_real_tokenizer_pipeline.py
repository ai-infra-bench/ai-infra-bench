#!/usr/bin/env python3
"""Run MiniMax reasoning parsing with the pinned real tokenizer metadata."""

from __future__ import annotations

from transformers import AutoTokenizer

from vllm.reasoning.minimax_m3_reasoning_parser import MiniMaxM3ReasoningParser


MODEL_PATH = "/opt/models/minimax-m3"


def _runtime_ids(tokenizer, chunk):
    if chunk == "<mm:think>":
        return tokenizer.encode("<mm:", add_special_tokens=False) + tokenizer.encode(
            "think>", add_special_tokens=False
        )
    if chunk == "</mm:think>":
        return tokenizer.encode("</mm:", add_special_tokens=False) + tokenizer.encode(
            "think>", add_special_tokens=False
        )
    return tokenizer.encode(chunk, add_special_tokens=False)


def _run(tokenizer, chunks):
    parser = MiniMaxM3ReasoningParser(tokenizer)
    previous_text = ""
    previous_ids = []
    reasoning = []
    content = []
    states = []
    for chunk in chunks:
        delta_ids = _runtime_ids(tokenizer, chunk)
        current_text = previous_text + chunk
        current_ids = previous_ids + delta_ids
        delta = parser.extract_reasoning_streaming(
            previous_text=previous_text,
            current_text=current_text,
            delta_text=chunk,
            previous_token_ids=previous_ids,
            current_token_ids=current_ids,
            delta_token_ids=delta_ids,
        )
        states.append(parser.is_reasoning_end_streaming(current_ids, delta_ids))
        if delta is not None:
            if delta.reasoning is not None:
                reasoning.append(delta.reasoning)
            if delta.content is not None:
                content.append(delta.content)
        previous_text = current_text
        previous_ids = current_ids
    return "".join(reasoning), "".join(content), states


def main() -> int:
    try:
        tokenizer = AutoTokenizer.from_pretrained(
            MODEL_PATH,
            trust_remote_code=True,
            local_files_only=True,
        )
        assert tokenizer.get_vocab()["<mm:think>"] == 200059
        assert tokenizer.get_vocab()["</mm:think>"] == 200060

        exact = _run(
            tokenizer,
            ["<mm:think>", "Reasoning", " content", "</mm:think>", "answer"],
        )
        split_delta = _run(
            tokenizer,
            ["<mm:", "think>", "plan", "</mm:", "think>", "answer"],
        )
        assert exact[0] == "Reasoning content"
        assert exact[1] == "answer"
        assert exact[2] == [False, False, False, True, True]
        assert split_delta[0] == "plan"
        assert split_delta[1] == "answer"
        assert split_delta[2][-1] is True
        assert "<mm:think>" not in exact[1] + split_delta[1]
        assert "</mm:think>" not in exact[1] + split_delta[1]
        print(
            {
                "entrypoint": "MiniMaxM3ReasoningParser with real tokenizer",
                "atomic_vocab_ids": [200059, 200060],
                "exact_issue_chunks": len(exact[2]),
                "cross_delta_chunks": len(split_delta[2]),
                "reasoning": [exact[0], split_delta[0]],
                "content": [exact[1], split_delta[1]],
            },
            flush=True,
        )
        return 0
    except Exception as exc:
        lines = str(exc).splitlines()
        print(
            {
                "error": type(exc).__name__,
                "message": lines[0] if lines else "no exception message",
            },
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
