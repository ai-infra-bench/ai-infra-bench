import string
from collections.abc import Sequence

import pytest

from vllm.entrypoints.openai.chat_completion.protocol import ChatCompletionRequest
from vllm.entrypoints.openai.chat_completion.protocol import (
    ChatCompletionToolsParam,
    FunctionDefinition,
)
from vllm.parser.parser_manager import ParserManager


class MiniMaxTokenizer:
    special_tokens = ("<mm:think>", "</mm:think>")

    def __init__(self):
        self.model_tokenizer = self
        self._token_to_id = {}
        self._id_to_token = {}
        for token in self.special_tokens:
            self._add_token(token)
        for char in string.printable:
            self._add_token(char)

    def _add_token(self, token):
        token_id = self._token_to_id.get(token)
        if token_id is None:
            token_id = len(self._token_to_id) + 1
            self._token_to_id[token] = token_id
            self._id_to_token[token_id] = token
        return token_id

    def get_vocab(self):
        return dict(self._token_to_id)

    def tokenize(self, text):
        tokens = []
        position = 0
        while position < len(text):
            for marker in self.special_tokens:
                if text.startswith(marker, position):
                    tokens.append(marker)
                    position += len(marker)
                    break
            else:
                tokens.append(text[position])
                position += 1
        return tokens

    def encode(self, text, add_special_tokens=False, **_kwargs):
        return [self._add_token(token) for token in self.tokenize(text)]

    def decode(self, ids: Sequence[int] | int, skip_special_tokens=False):
        if isinstance(ids, int):
            ids = [ids]
        return "".join(self._id_to_token[token_id] for token_id in ids)

    def convert_ids_to_tokens(self, ids, skip_special_tokens=False):
        return [self._id_to_token[token_id] for token_id in ids]

    def convert_tokens_to_ids(self, tokens):
        if isinstance(tokens, str):
            return self._add_token(tokens)
        return [self._add_token(token) for token in tokens]

    def convert_tokens_to_string(self, tokens):
        return "".join(tokens)


class RuntimeSplitTokenizer(MiniMaxTokenizer):
    def encode_runtime(self, text):
        return [self._add_token(character) for character in text]


def _request(tools=None, stream=True):
    return ChatCompletionRequest(
        messages=[{"role": "user", "content": "Investigate the incident."}],
        model="MiniMaxAI/MiniMax-M3-MXFP8",
        stream=stream,
        tools=tools,
        tool_choice="auto" if tools else None,
    )


def _parser(tokenizer=None, tools=None, thinking_mode=None):
    tokenizer = tokenizer or MiniMaxTokenizer()
    parser_cls = ParserManager.get_parser(
        tool_parser_name="minimax_m3" if tools else None,
        reasoning_parser_name="minimax_m3",
        enable_auto_tools=bool(tools),
        model_name="MiniMaxAI/MiniMax-M3-MXFP8",
    )
    assert parser_cls is not None
    chat_template_kwargs = (
        {"thinking_mode": thinking_mode} if thinking_mode is not None else {}
    )
    return (
        parser_cls(
            tokenizer,
            tools or [],
            chat_template_kwargs=chat_template_kwargs,
        ),
        tokenizer,
    )


def _stream(parser, tokenizer, chunks, split_runtime=False, request=None):
    request = request or _request()
    deltas = []
    for index, chunk in enumerate(chunks):
        delta_ids = (
            tokenizer.encode_runtime(chunk)
            if split_runtime
            else tokenizer.encode(chunk, add_special_tokens=False)
        )
        delta = parser.parse_delta(
            chunk,
            delta_ids,
            request,
            finished=index == len(chunks) - 1,
        )
        if delta is not None:
            deltas.append(delta)
    reasoning = "".join(delta.reasoning or "" for delta in deltas) or None
    content = "".join(delta.content or "" for delta in deltas) or None
    tool_calls = [call for delta in deltas for call in delta.tool_calls or []]
    return reasoning, content, tool_calls


@pytest.mark.parametrize(
    "chunks,expected_reasoning,expected_content",
    [
        (["<mm:think>", "Reasoning", " content", "</mm:think>", "answer"], "Reasoning content", "answer"),
        (["<mm:think>Reasoning</mm:think>answer"], "Reasoning", "answer"),
        (["<mm:think>", "Reasoning</mm:think>answer"], "Reasoning", "answer"),
        (["<mm:think>Reasoning", "</mm:think>", "answer"], "Reasoning", "answer"),
        (["<mm:think>", "检查部署记录 ✓", "</mm:think>", "done"], "检查部署记录 ✓", "done"),
    ],
    ids=["separate", "single-delta", "combined-end", "separate-end", "unicode"],
)
def test_visible_markers_encoded_as_runtime_pieces(
    chunks, expected_reasoning, expected_content
):
    parser, tokenizer = _parser(RuntimeSplitTokenizer())

    reasoning, content, tool_calls = _stream(
        parser, tokenizer, chunks, split_runtime=True
    )

    assert reasoning == expected_reasoning
    assert content == expected_content
    assert tool_calls == []
    assert "<mm:think>" not in (content or "")
    assert "</mm:think>" not in (content or "")


@pytest.mark.parametrize(
    "chunks",
    [
        ["<mm:", "think>", "plan", "</mm:", "think>", "answer"],
        ["<", "mm:think>", "plan", "</", "mm:think>", "answer"],
        ["<mm:thi", "nk>plan</mm:thi", "nk>answer"],
        ["<mm:t", "h", "ink>plan</mm:t", "h", "ink>answer"],
    ],
    ids=["two-parts", "uneven", "inside-content", "many-small-parts"],
)
def test_markers_split_across_streaming_deltas(chunks):
    parser, tokenizer = _parser(RuntimeSplitTokenizer())

    reasoning, content, tool_calls = _stream(
        parser, tokenizer, chunks, split_runtime=True
    )

    assert reasoning == "plan"
    assert content == "answer"
    assert tool_calls == []
    assert all(
        marker not in (reasoning or "") + (content or "")
        for marker in tokenizer.special_tokens
    )


@pytest.mark.parametrize(
    "chunks,expected_reasoning,expected_content",
    [
        (["<mm:think>", "plan", "</mm:think>", "answer"], "plan", "answer"),
        (["<mm:think>plan</mm:think>answer"], "plan", "answer"),
        (["plain ", "answer"], None, "plain answer"),
    ],
    ids=["atomic-separate", "atomic-combined", "plain"],
)
def test_existing_streaming_outputs_remain_unchanged(
    chunks, expected_reasoning, expected_content
):
    parser, tokenizer = _parser()

    reasoning, content, tool_calls = _stream(parser, tokenizer, chunks)

    assert reasoning == expected_reasoning
    assert content == expected_content
    assert tool_calls == []


@pytest.mark.parametrize(
    "chunks,expected_content",
    [
        (["plain <"], "plain <"),
        (["plain <mm:"], "plain <mm:"),
        (["plain <mm:", "not-a-marker"], "plain <mm:not-a-marker"),
        (["plain </mm:"], "plain </mm:"),
    ],
    ids=["less-than", "start-prefix-at-finish", "invalid-start-prefix", "end-prefix"],
)
def test_incomplete_marker_like_content_remains_visible(chunks, expected_content):
    parser, tokenizer = _parser()

    reasoning, content, tool_calls = _stream(parser, tokenizer, chunks)

    assert reasoning is None
    assert content == expected_content
    assert tool_calls == []


@pytest.mark.parametrize(
    "tokenizer,split_runtime",
    [(MiniMaxTokenizer(), False), (RuntimeSplitTokenizer(), True)],
    ids=["atomic-marker", "runtime-pieces"],
)
def test_existing_prefilled_reasoning_mode_remains_unchanged(
    tokenizer, split_runtime
):
    parser, tokenizer = _parser(tokenizer, thinking_mode="enabled")

    reasoning, content, tool_calls = _stream(
        parser,
        tokenizer,
        ["plan", "</mm:think>", "answer"],
        split_runtime=split_runtime,
    )

    assert reasoning == "plan"
    assert content == "answer"
    assert tool_calls == []


def test_disabled_thinking_mode_remains_plain_content():
    parser, tokenizer = _parser(thinking_mode="disabled")

    reasoning, content, tool_calls = _stream(
        parser,
        tokenizer,
        ["plain ", "answer"],
    )

    assert reasoning is None
    assert content == "plain answer"
    assert tool_calls == []


@pytest.mark.parametrize(
    "output,expected_reasoning,expected_content",
    [
        ("<mm:think>plan</mm:think>answer", "plan", "answer"),
        ("plain answer", None, "plain answer"),
        ("</mm:think>answer", None, "answer"),
    ],
)
def test_nonstreaming_outputs_remain_unchanged(
    output, expected_reasoning, expected_content
):
    parser, _ = _parser()

    reasoning, content, tool_calls = parser.parse(output, _request(stream=False))

    assert reasoning == expected_reasoning
    assert content == expected_content
    assert tool_calls == []


@pytest.mark.parametrize(
    "tool_name,argument_name,argument_value,reasoning_text",
    [
        (
            "search_incident_runbooks",
            "service",
            "checkout-api",
            "I should search the current runbook first.",
        ),
        (
            "lookup_deployment",
            "release",
            "checkout-2026.08.31",
            "I need to inspect the deployed release.",
        ),
        (
            "query_service_logs",
            "query",
            "status:502 AND service:edge-gateway",
            "I should query recent gateway errors.",
        ),
    ],
    ids=["instruction-example", "different-tool", "punctuated-argument"],
)
def test_streaming_reasoning_and_structured_tool_calls(
    tool_name, argument_name, argument_value, reasoning_text
):
    tokenizer = RuntimeSplitTokenizer()
    tools = [
        ChatCompletionToolsParam(
            function=FunctionDefinition(
                name=tool_name,
                parameters={
                    "type": "object",
                    "properties": {argument_name: {"type": "string"}},
                    "required": [argument_name],
                },
            )
        )
    ]
    request = _request(tools=tools)
    parser, tokenizer = _parser(tokenizer, tools=tools)
    ns = "]<]minimax[>["
    tool_text = (
        f"{ns}<tool_call>\n"
        f'{ns}<invoke name="{tool_name}">'
        f"{ns}<{argument_name}>{argument_value}{ns}</{argument_name}>"
        f"{ns}</invoke>\n"
        f"{ns}</tool_call>"
    )
    chunks = [
        "<mm:",
        "think>",
        reasoning_text,
        "</mm:",
        "think>",
        tool_text,
    ]

    reasoning, content, tool_calls = _stream(
        parser,
        tokenizer,
        chunks,
        split_runtime=True,
        request=request,
    )

    assert reasoning == reasoning_text
    assert content is None
    assert len(tool_calls) == 1
    assert tool_calls[0].function.name == tool_name
    assert tool_calls[0].function.arguments == (
        "{" + f'"{argument_name}":"{argument_value}"' + "}"
    )
