import string
from collections.abc import Sequence

import pytest

from vllm.entrypoints.openai.chat_completion.protocol import ChatCompletionRequest
from vllm.entrypoints.openai.chat_completion.protocol import (
    ChatCompletionToolsParam,
    FunctionDefinition,
)
from vllm.parser.abstract_parser import DelegatingParser, StreamState
from vllm.reasoning.minimax_m3_reasoning_parser import MiniMaxM3ReasoningParser
from vllm.tool_parsers.minimax_m3_tool_parser import MinimaxM3ToolParser


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


class AlwaysSplitTokenizer(MiniMaxTokenizer):
    def tokenize(self, text):
        return list(text)


def _parser(tokenizer=None, mode=None):
    tokenizer = tokenizer or MiniMaxTokenizer()
    kwargs = {} if mode is None else {"thinking_mode": mode}
    return MiniMaxM3ReasoningParser(tokenizer, chat_template_kwargs=kwargs), tokenizer


def _stream(parser, tokenizer, chunks, split_runtime=False):
    previous_text = ""
    previous_ids = []
    reasoning_parts = []
    content_parts = []
    end_states = []
    for chunk in chunks:
        if split_runtime:
            delta_ids = tokenizer.encode_runtime(chunk)
        else:
            delta_ids = tokenizer.encode(chunk, add_special_tokens=False)
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
        end_states.append(parser.is_reasoning_end_streaming(current_ids, delta_ids))
        if delta is not None:
            if delta.reasoning is not None:
                reasoning_parts.append(delta.reasoning)
            if delta.content is not None:
                content_parts.append(delta.content)
        previous_text = current_text
        previous_ids = current_ids
    return "".join(reasoning_parts) or None, "".join(content_parts) or None, end_states


@pytest.mark.parametrize(
    "chunks,expected_states",
    [
        (["<mm:think>", "Reasoning", " content", "</mm:think>", "answer"], [False, False, False, True, True]),
        (["<mm:think>Reasoning</mm:think>answer"], [True]),
        (["<mm:think>", "Reasoning</mm:think>answer"], [False, True]),
        (["<mm:think>Reasoning", "</mm:think>", "answer"], [False, True, True]),
    ],
    ids=["separate", "single-delta", "combined-end", "separate-end"],
)
def test_split_runtime_markers_route_reasoning_and_content(chunks, expected_states):
    parser, tokenizer = _parser(RuntimeSplitTokenizer())

    reasoning, content, states = _stream(parser, tokenizer, chunks, split_runtime=True)

    assert reasoning == "Reasoning content" or reasoning == "Reasoning"
    assert content == "answer"
    assert states == expected_states


@pytest.mark.parametrize(
    "chunks",
    [
        ["<mm:", "think>", "plan", "</mm:", "think>", "answer"],
        ["<", "mm:think>", "plan", "</", "mm:think>", "answer"],
        ["<mm:thi", "nk>plan</mm:thi", "nk>answer"],
    ],
    ids=["two-parts", "uneven", "inside-content"],
)
def test_marker_text_split_across_network_deltas(chunks):
    parser, tokenizer = _parser(RuntimeSplitTokenizer())

    reasoning, content, states = _stream(parser, tokenizer, chunks, split_runtime=True)

    assert reasoning == "plan"
    assert content == "answer"
    assert states[-1] is True
    assert all(marker not in (reasoning or "") + (content or "") for marker in tokenizer.special_tokens)


@pytest.mark.parametrize("mode", ["enabled", None])
def test_split_runtime_enabled_and_adaptive_modes(mode):
    parser, tokenizer = _parser(RuntimeSplitTokenizer(), mode=mode)
    chunks = ["plan", "</mm:think>", "answer"] if mode else ["<mm:think>", "plan", "</mm:think>", "answer"]

    reasoning, content, states = _stream(parser, tokenizer, chunks, split_runtime=True)

    assert reasoning == "plan"
    assert content == "answer"
    assert states[-1] is True


@pytest.mark.parametrize(
    "chunks",
    [
        ["<mm:think>", "plan", "</mm:think>", "answer"],
        ["<mm:think>plan</mm:think>answer"],
        ["plain ", "answer"],
    ],
    ids=["atomic-separate", "atomic-combined", "plain"],
)
def test_existing_atomic_and_plain_streaming_behavior(chunks):
    parser, tokenizer = _parser()

    reasoning, content, states = _stream(parser, tokenizer, chunks)

    if "think" in "".join(chunks):
        assert reasoning == "plan"
        assert content == "answer"
    else:
        assert reasoning is None
        assert content == "plain answer"
    assert states[-1] is True


@pytest.mark.parametrize(
    "output,expected_reasoning,expected_content",
    [
        ("<mm:think>plan</mm:think>answer", "plan", "answer"),
        ("plain answer", None, "plain answer"),
        ("</mm:think>answer", None, "answer"),
    ],
)
def test_nonstreaming_behavior_is_unchanged(output, expected_reasoning, expected_content):
    parser, _ = _parser()
    request = ChatCompletionRequest(messages=[], model="test")

    assert parser.extract_reasoning(output, request) == (
        expected_reasoning,
        expected_content,
    )


def test_token_helpers_recognize_split_marker_sequences():
    parser, tokenizer = _parser(AlwaysSplitTokenizer())
    ids = tokenizer.encode("<mm:think>abc</mm:think>def", add_special_tokens=False)
    open_ids = tokenizer.encode("<mm:think>abc", add_special_tokens=False)

    assert parser.is_reasoning_end(ids) is True
    assert parser.is_reasoning_end(open_ids) is False
    assert tokenizer.decode(parser.extract_content_ids(ids)) == "def"
    assert parser.extract_content_ids(open_ids) == []
    assert parser.count_reasoning_tokens(ids) == len(tokenizer.encode("abc"))


def test_streamed_mcp_runbook_request_preserves_structured_tool_call():
    tokenizer = RuntimeSplitTokenizer()
    tools = [
        ChatCompletionToolsParam(
            function=FunctionDefinition(
                name="search_incident_runbooks",
                parameters={
                    "type": "object",
                    "properties": {
                        "service": {"type": "string"},
                        "symptom": {"type": "string"},
                    },
                    "required": ["service", "symptom"],
                },
            )
        )
    ]
    request = ChatCompletionRequest(
        messages=[
            {
                "role": "user",
                "content": (
                    "Checkout API is returning elevated 502s. Search the current "
                    "incident runbooks for mitigation steps before answering."
                ),
            }
        ],
        model="MiniMaxAI/MiniMax-M3-MXFP8",
        stream=True,
        tools=tools,
        tool_choice="auto",
    )
    parser = DelegatingParser(tokenizer)
    parser._reasoning_parser = MiniMaxM3ReasoningParser(tokenizer)
    parser._tool_parser = MinimaxM3ToolParser(tokenizer, tools=tools)
    parser._engine_based = False
    parser._stream_state = StreamState(engine_based=False)
    ns = "]<]minimax[>["
    tool_text = (
        f"{ns}<tool_call>\n"
        f'{ns}<invoke name="search_incident_runbooks">'
        f"{ns}<service>checkout-api{ns}</service>"
        f"{ns}<symptom>elevated 502s{ns}</symptom>"
        f"{ns}</invoke>\n"
        f"{ns}</tool_call>"
    )
    chunks = [
        "<mm:think>",
        "I should search the current checkout incident runbook first.",
        "</mm:think>",
        tool_text,
    ]
    deltas = []
    for index, chunk in enumerate(chunks):
        delta = parser.parse_delta(
            chunk,
            tokenizer.encode_runtime(chunk),
            request,
            finished=index == len(chunks) - 1,
        )
        if delta is not None:
            deltas.append(delta)

    assert "".join(delta.reasoning or "" for delta in deltas) == (
        "I should search the current checkout incident runbook first."
    )
    visible_content = "".join(delta.content or "" for delta in deltas)
    assert "<mm:think>" not in visible_content
    assert "</mm:think>" not in visible_content
    tool_calls = [call for delta in deltas for call in delta.tool_calls or []]
    assert len(tool_calls) == 1
    assert tool_calls[0].function.name == "search_incident_runbooks"
    assert tool_calls[0].function.arguments == (
        '{"service":"checkout-api","symptom":"elevated 502s"}'
    )
