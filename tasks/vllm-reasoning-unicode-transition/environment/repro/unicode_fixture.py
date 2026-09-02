from __future__ import annotations

from vllm.entrypoints.openai.chat_completion.protocol import ChatCompletionRequest
from vllm.parser.abstract_parser import DelegatingParser
from vllm.parser.engine.registered_adapters import (
    Glm47MoeParserReasoningAdapter,
    Glm47MoeParserToolAdapter,
)


class ByteFallbackTokenizer:
    def __init__(self):
        self._vocab = {"<think>": 50, "</think>": 51, "<tool_call>": 60, "</tool_call>": 61, "<arg_key>": 62, "</arg_key>": 63, "<arg_value>": 64, "</arg_value>": 65}
        self._text = {100: "Let me", 101: " think", 51: "</think>", 200: "삼성", 201: "전자의", 202: " 주가입니다."}
        self.eos_token_id = None
        self.bos_token_id = None
        self.pad_token_id = None

    def get_vocab(self):
        return dict(self._vocab)

    def encode(self, _text, **_kwargs):
        return list(self._text)

    def decode(self, ids, **_kwargs):
        return "".join("�" if token_id == 200 else self._text[token_id] for token_id in ids)


class Parser(DelegatingParser):
    reasoning_parser_cls = Glm47MoeParserReasoningAdapter
    tool_parser_cls = Glm47MoeParserToolAdapter


def run():
    tokens = [(100, "Let me"), (101, " think"), (51, "</think>"), (200, "삼성"), (201, "전자의"), (202, " 주가입니다.")]
    parser = Parser(ByteFallbackTokenizer())
    request = ChatCompletionRequest(model="local", messages=[{"role": "user", "content": "test"}])
    reasoning = []
    content = []
    chunk_size = 2
    for start in range(0, len(tokens), chunk_size):
        part = tokens[start : start + chunk_size]
        delta = parser.parse_delta(
            "".join(text for _, text in part),
            [token_id for token_id, _ in part],
            request,
            prompt_token_ids=[] if start == 0 else None,
            finished=start + chunk_size >= len(tokens),
        )
        if delta and delta.reasoning:
            reasoning.append(delta.reasoning)
        if delta and delta.content:
            content.append(delta.content)
    return "".join(reasoning), "".join(content)
