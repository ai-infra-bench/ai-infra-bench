from __future__ import annotations

from dataclasses import dataclass

from vllm.entrypoints.openai.chat_completion.protocol import ChatCompletionRequest
from vllm.parser.abstract_parser import DelegatingParser
from vllm.parser.engine.registered_adapters import (
    Glm47MoeParserReasoningAdapter,
    Glm47MoeParserToolAdapter,
    Qwen3ParserReasoningAdapter,
    Qwen3ParserToolAdapter,
)


class ByteFallbackTokenizer:
    def __init__(self, vocab, tokens, fallback_ids=()):
        self._vocab = dict(vocab)
        self._ids = [token_id for token_id, _ in tokens]
        self._text = {token_id: text for token_id, text in tokens}
        self._fallback_ids = frozenset(fallback_ids)
        self._special_ids = set(vocab.values())
        self.eos_token_id = None
        self.bos_token_id = None
        self.pad_token_id = None

    def get_vocab(self):
        return dict(self._vocab)

    def encode(self, _text, **_kwargs):
        return list(self._ids)

    def decode(self, ids, skip_special_tokens=False):
        parts = []
        for token_id in ids:
            if skip_special_tokens and token_id in self._special_ids:
                continue
            parts.append("�" if token_id in self._fallback_ids else self._text[token_id])
        return "".join(parts)


class GlmDelegatingParser(DelegatingParser):
    reasoning_parser_cls = Glm47MoeParserReasoningAdapter
    tool_parser_cls = Glm47MoeParserToolAdapter


class QwenDelegatingParser(DelegatingParser):
    reasoning_parser_cls = Qwen3ParserReasoningAdapter
    tool_parser_cls = Qwen3ParserToolAdapter


VOCAB = {
    "<think>": 50,
    "</think>": 51,
    "<tool_call>": 60,
    "</tool_call>": 61,
    "<arg_key>": 62,
    "</arg_key>": 63,
    "<arg_value>": 64,
    "</arg_value>": 65,
}


@dataclass
class Parsed:
    reasoning: str
    content: str
    tool_names: list[str]
    tool_arguments: list[str]


def request(tools=None):
    return ChatCompletionRequest(
        model="local-parser",
        messages=[{"role": "user", "content": "test"}],
        tools=tools,
    )


def parse(parser_cls, tokens, fallback_ids=(), chunk_size=1, tools=None):
    tokenizer = ByteFallbackTokenizer(VOCAB, tokens, fallback_ids)
    parser = parser_cls(tokenizer)
    req = request(tools)
    if chunk_size is None:
        chunk_size = len(tokens)
    deltas = []
    for start in range(0, len(tokens), chunk_size):
        part = tokens[start : start + chunk_size]
        deltas.append(
            parser.parse_delta(
                "".join(text for _, text in part),
                [token_id for token_id, _ in part],
                req,
                prompt_token_ids=[] if start == 0 else None,
                finished=start + chunk_size >= len(tokens),
            )
        )
    reasoning = []
    content = []
    calls: dict[int, dict] = {}
    for delta in deltas:
        if delta is None:
            continue
        if delta.reasoning:
            reasoning.append(delta.reasoning)
        if delta.content:
            content.append(delta.content)
        for call in delta.tool_calls or []:
            entry = calls.setdefault(call.index, {"name": "", "arguments": []})
            if call.function and call.function.name:
                entry["name"] = call.function.name
            if call.function and call.function.arguments:
                entry["arguments"].append(call.function.arguments)
    return Parsed(
        reasoning="".join(reasoning),
        content="".join(content),
        tool_names=[item["name"] for item in calls.values()],
        tool_arguments=["".join(item["arguments"]) for item in calls.values()],
    )


def korean_tokens():
    return [
        (100, "Let me"),
        (101, " think"),
        (51, "</think>"),
        (200, "삼성"),
        (201, "전자의"),
        (202, " 주가입니다."),
    ]
