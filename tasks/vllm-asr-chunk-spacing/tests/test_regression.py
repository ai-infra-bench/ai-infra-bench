import json
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vllm.config import ModelConfig
from vllm.config.speech_to_text import SpeechToTextConfig
from vllm.entrypoints.openai.engine.protocol import ErrorResponse, RequestResponseMetadata
from vllm.entrypoints.openai.models.serving import OpenAIServingModels
from vllm.entrypoints.openai.speech_to_text import speech_to_text as speech_module
from vllm.entrypoints.openai.speech_to_text.protocol import TranscriptionRequest
from vllm.entrypoints.openai.speech_to_text.serving import (
    OpenAIServingTranscription,
    OpenAIServingTranslation,
)
from vllm.entrypoints.openai.speech_to_text.speech_to_text import OpenAISpeechToText
from vllm.model_executor.models.interfaces import SupportsTranscription
from vllm.outputs import CompletionOutput, RequestOutput


class StubTranscriptionModel:
    no_space_languages = {"ja", "zh"}
    supports_segment_timestamp = False

    @classmethod
    def get_speech_to_text_config(cls, model_config: ModelConfig, task_type: str):
        return SpeechToTextConfig(sample_rate=16000.0, max_audio_clip_s=5.0)

    @classmethod
    def post_process_output(cls, text):
        return text


def _output(text):
    return RequestOutput(
        request_id="rid",
        prompt=None,
        prompt_token_ids=None,
        prompt_logprobs=None,
        outputs=[
            CompletionOutput(
                index=0,
                text=text,
                token_ids=(1,),
                cumulative_logprob=None,
                logprobs=None,
                finish_reason="stop",
            )
        ],
        finished=True,
    )


def _generator(*parts):
    async def generate() -> AsyncGenerator[RequestOutput, None]:
        for part in parts:
            yield _output(part)

    return generate()


def _contents(sse):
    values = []
    for line in sse.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line.removeprefix("data: ").strip()
        if payload == "[DONE]":
            continue
        for choice in (json.loads(payload).get("choices") or []):
            delta = choice.get("delta") or {}
            if "content" in delta:
                values.append(delta["content"])
    return values


@pytest.mark.parametrize(
    "language,expected",
    [("en", " "), (None, " "), ("zh", ""), ("ja", "")],
)
def test_language_separator_contract(language, expected):
    separator = getattr(speech_module, "asr_inter_chunk_separator")
    assert separator(language, SupportsTranscription.no_space_languages) == expected


async def _stream(serving_cls, method_name, language, chunks):
    serving = serving_cls.__new__(serving_cls)
    serving.enable_force_include_usage = False
    serving.model_cls = StubTranscriptionModel
    serving.task_type = "transcribe" if serving_cls is OpenAIServingTranscription else "translate"
    request = SimpleNamespace(
        model="stub-model",
        stream_include_usage=False,
        stream_continuous_usage_stats=False,
    )
    separator = getattr(speech_module, "asr_inter_chunk_separator")(
        language,
        StubTranscriptionModel.no_space_languages,
    )
    generators = [_generator(*parts) for parts in chunks]
    method = getattr(serving_cls, method_name)
    lines = []
    async for line in method(
        serving,
        request=request,
        result_generator=generators,
        request_id="request",
        request_metadata=RequestResponseMetadata(request_id="request"),
        audio_duration_s=1.0,
        separator=separator,
    ):
        lines.append(line)
    return "".join(_contents("".join(lines)))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "language,chunks,expected",
    [
        ("en", [("Hello, this",), ("is vLLM",)], "Hello, this is vLLM"),
        (None, [("one",), ("two",), ("three",)], "one two three"),
        ("zh", [("你好",), ("世界",)], "你好世界"),
        ("ja", [("こん",), ("にちは",)], "こんにちは"),
    ],
)
async def test_streaming_transcription_chunk_boundaries(language, chunks, expected):
    assert await _stream(
        OpenAIServingTranscription,
        "transcription_stream_generator",
        language,
        chunks,
    ) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "language,expected",
    [("en", "hello world"), ("zh", "你好世界")],
)
async def test_streaming_translation_chunk_boundaries(language, expected):
    chunks = [("hello",), ("world",)] if language == "en" else [("你好",), ("世界",)]
    assert await _stream(
        OpenAIServingTranslation,
        "translation_stream_generator",
        language,
        chunks,
    ) == expected


@pytest.mark.asyncio
async def test_separator_is_added_once_per_audio_chunk():
    await _assert_multidelta_stream()


async def _assert_multidelta_stream():
    text = await _stream(
        OpenAIServingTranscription,
        "transcription_stream_generator",
        "en",
        [("hel", "lo"), ("wor", "ld")],
    )
    assert text == "hello world"


@pytest.mark.asyncio
@pytest.mark.parametrize("language,expected", [("en", "hello world"), ("zh", "你好世界")])
async def test_nonstreaming_public_transcription_path(language, expected):
    first, second = (("hello", "world") if language == "en" else ("你好", "世界"))
    engine = MagicMock()
    engine.model_config = MagicMock()
    engine.model_config.get_diff_sampling_param.return_value = {
        "max_tokens": 256,
        "temperature": 0.0,
    }
    engine.model_config.max_model_len = 8192
    engine.errored = False
    engine.generate.side_effect = [_generator(first), _generator(second)]
    models = MagicMock(spec=OpenAIServingModels)
    models.lora_requests = {}
    models.is_base_model.return_value = True
    preprocess = AsyncMock(return_value=([MagicMock(), MagicMock()], 1.0))

    with (
        patch("vllm.model_executor.model_loader.get_model_cls", return_value=StubTranscriptionModel),
        patch.object(OpenAISpeechToText, "_preprocess_speech_to_text", preprocess),
    ):
        serving = OpenAIServingTranscription(engine, models, request_logger=None)
        request = TranscriptionRequest.model_construct(
            file=MagicMock(),
            model="stub-model",
            language=language,
            stream=False,
            response_format="json",
        )
        response = await serving.create_transcription(b"RIFF", request, raw_request=None)

    assert not isinstance(response, ErrorResponse)
    assert response.text == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("serving_cls,method", [(OpenAIServingTranscription, "transcription_stream_generator"), (OpenAIServingTranslation, "translation_stream_generator")])
async def test_single_chunk_has_no_leading_separator(serving_cls, method):
    assert await _stream(serving_cls, method, "en", [("hello",)]) == "hello"
