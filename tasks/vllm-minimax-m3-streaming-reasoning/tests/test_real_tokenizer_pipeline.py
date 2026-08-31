#!/usr/bin/env python3
"""Exercise the registered MiniMax parser with the pinned tokenizer metadata."""

from __future__ import annotations

from transformers import AutoTokenizer

from vllm.entrypoints.openai.chat_completion.protocol import ChatCompletionRequest
from vllm.parser.parser_manager import ParserManager


MODEL_PATH = "/opt/models/minimax-m3"


def _run(tokenizer, chunks):
    parser_cls = ParserManager.get_parser(
        reasoning_parser_name="minimax_m3",
        model_name="MiniMaxAI/MiniMax-M3-MXFP8",
    )
    assert parser_cls is not None
    parser = parser_cls(tokenizer)
    request = ChatCompletionRequest(
        messages=[{"role": "user", "content": "Summarize the incident."}],
        model="MiniMaxAI/MiniMax-M3-MXFP8",
        stream=True,
    )
    reasoning = []
    content = []
    for index, chunk in enumerate(chunks):
        delta = parser.parse_delta(
            chunk,
            tokenizer.encode(chunk, add_special_tokens=False),
            request,
            finished=index == len(chunks) - 1,
        )
        if delta is not None:
            reasoning.append(delta.reasoning or "")
            content.append(delta.content or "")
    return "".join(reasoning), "".join(content)


def main() -> int:
    try:
        tokenizer = AutoTokenizer.from_pretrained(
            MODEL_PATH,
            trust_remote_code=True,
            local_files_only=True,
        )
        assert tokenizer.get_vocab()["<mm:think>"] == 200059
        assert tokenizer.get_vocab()["</mm:think>"] == 200060

        runtime_split = _run(
            tokenizer,
            ["<mm:think>", "Reasoning", " content", "</mm:think>", "answer"],
        )
        network_split = _run(
            tokenizer,
            ["<mm:", "think>", "plan", "</mm:", "think>", "answer"],
        )
        unicode_case = _run(
            tokenizer,
            ["<mm:thi", "nk>检查日志 ✓</mm:thi", "nk>done"],
        )
        assert runtime_split == ("Reasoning content", "answer")
        assert network_split == ("plan", "answer")
        assert unicode_case == ("检查日志 ✓", "done")
        for reasoning, content in (runtime_split, network_split, unicode_case):
            assert "<mm:think>" not in reasoning + content
            assert "</mm:think>" not in reasoning + content
        print(
            {
                "entrypoint": "ParserManager registered MiniMax parser",
                "atomic_vocab_ids": [200059, 200060],
                "reasoning": [runtime_split[0], network_split[0], unicode_case[0]],
                "content": [runtime_split[1], network_split[1], unicode_case[1]],
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
