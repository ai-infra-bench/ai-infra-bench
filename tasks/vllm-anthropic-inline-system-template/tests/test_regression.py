import pytest

from vllm.entrypoints.anthropic.protocol import AnthropicMessagesRequest
from vllm.entrypoints.anthropic.serving import AnthropicServingMessages
from vllm.entrypoints.openai.chat_completion.serving import OpenAIServingChat


RESTRICTIVE_TEMPLATE = (
    "{%- for message in messages %}"
    "{%- if message.role == 'system' and not loop.first %}"
    "{{- raise_exception('System message must be first') }}"
    "{%- endif %}"
    "{{- message.role }}:{{ message.content }};"
    "{%- endfor %}"
)
PERMISSIVE_TEMPLATE = (
    "{%- for message in messages %}"
    "{{- message.role }}:{{ message.content }};"
    "{%- endfor %}"
)


def _request():
    return AnthropicMessagesRequest(
        model="test-model",
        max_tokens=32,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Please check the GPU status for vLLM."},
            {"role": "assistant", "content": "Sure, I will check it."},
            {"role": "user", "content": "Show me the nvidia-smi output."},
            {
                "role": "assistant",
                "content": "The GPU status looks normal, with utilization around 15%.",
            },
            {"role": "user", "content": "Write up the results as a report."},
            {
                "role": "system",
                "content": "Task instruction: Based on the conversation above, generate a brief GPU status report.",
            },
            {"role": "user", "content": "Please summarize the above."},
        ],
    )


def _service(monkeypatch, template):
    def initialize_parent(self, *args, **kwargs):
        self.chat_template = kwargs.get("chat_template")

    monkeypatch.setattr(OpenAIServingChat, "__init__", initialize_parent)
    return AnthropicServingMessages(
        None,
        None,
        "assistant",
        openai_serving_render=None,
        request_logger=None,
        chat_template=template,
        chat_template_content_format="auto",
    )


def _assert_message_behavior(chat_request, *, should_merge):
    roles = [message["role"] for message in chat_request.messages]
    if should_merge:
        assert roles == [
            "system",
            "user",
            "assistant",
            "user",
            "assistant",
            "user",
            "user",
        ]
        assert chat_request.messages[0]["content"] == (
            "You are a helpful assistant."
            "Task instruction: Based on the conversation above, generate a brief GPU status report."
        )
    else:
        assert roles == [
            "system",
            "user",
            "assistant",
            "user",
            "assistant",
            "user",
            "system",
            "user",
        ]
        assert chat_request.messages[6]["content"].startswith("Task instruction:")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("template", "should_merge"),
    [
        (RESTRICTIVE_TEMPLATE, True),
        (PERMISSIVE_TEMPLATE, False),
        (None, True),
    ],
)
async def test_message_generation_adapts_to_template(
    monkeypatch, template, should_merge
):
    serving = _service(monkeypatch, template)
    captured = []

    async def create_chat_completion(chat_request, raw_request):
        captured.append(chat_request)
        return object()

    serving.create_chat_completion = create_chat_completion
    serving.message_stream_converter = lambda _generator: "stream-result"

    result = await serving.create_messages(_request())

    assert result == "stream-result"
    assert len(captured) == 1
    _assert_message_behavior(captured[0], should_merge=should_merge)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("template", "should_merge"),
    [
        (RESTRICTIVE_TEMPLATE, True),
        (PERMISSIVE_TEMPLATE, False),
        (None, True),
    ],
)
async def test_count_tokens_uses_the_same_template_behavior(
    monkeypatch, template, should_merge
):
    serving = _service(monkeypatch, template)
    captured = []

    async def render_chat_request(chat_request):
        captured.append(chat_request)
        return None, [{"prompt_token_ids": [1, 2, 3]}]

    serving.render_chat_request = render_chat_request

    result = await serving.count_tokens(_request())

    assert result.input_tokens == 3
    assert len(captured) == 1
    _assert_message_behavior(captured[0], should_merge=should_merge)
