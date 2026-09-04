from __future__ import annotations

import io
import json
import math
import wave
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from vllm.config import ModelConfig
from vllm.config.speech_to_text import SpeechToTextConfig
from vllm.entrypoints.openai.engine.protocol import ErrorResponse
from vllm.entrypoints.openai.models.serving import OpenAIServingModels
from vllm.entrypoints.openai.speech_to_text.protocol import (
    TranscriptionRequest,
    TranslationRequest,
)
from vllm.entrypoints.openai.speech_to_text.serving import (
    OpenAIServingTranscription,
    OpenAIServingTranslation,
)
from vllm.inputs import TokensPrompt
from vllm.model_executor.models.interfaces import SupportsTranscription
from vllm.model_executor.models.qwen3_asr import Qwen3ASRForConditionalGeneration
from vllm.outputs import CompletionOutput, RequestOutput


class StubTranscriptionModel(SupportsTranscription):
    supported_languages = {
        "en": "English",
        "ja": "Japanese",
        "zh": "Chinese",
    }
    supports_segment_timestamp = False

    @classmethod
    def validate_language(cls, language):
        return language

    @classmethod
    def get_speech_to_text_config(
        cls, model_config: ModelConfig, task_type: str
    ) -> SpeechToTextConfig:
        return SpeechToTextConfig(
            sample_rate=16000,
            max_audio_clip_s=2,
            overlap_chunk_second=1,
            min_energy_split_window_size=160,
        )

    @classmethod
    def get_generation_prompt(
        cls,
        audio,
        stt_config,
        model_config,
        language,
        task_type,
        request_prompt,
        to_language,
    ):
        return TokensPrompt(
            prompt_token_ids=[1],
            multi_modal_data={"audio": audio},
        )

    @classmethod
    def post_process_output(cls, text):
        return text


class StubQwen3Model(StubTranscriptionModel):
    @classmethod
    def post_process_output(cls, text):
        return Qwen3ASRForConditionalGeneration.post_process_output(text)


class StubRenderer:
    def __init__(self):
        self.prompt_count = 0

    async def render_cmpl_async(self, prompts):
        self.prompt_count = len(prompts)
        return [
            {"type": "tokens", "prompt_token_ids": [1]}
            for _ in prompts
        ]


@dataclass
class SpeechResult:
    text: str
    engine_calls: int
    prompt_count: int
    sse_objects: list[dict]
    done: bool


def make_wav(chunk_count: int) -> bytes:
    duration_s = 1.2 if chunk_count == 1 else chunk_count + 0.6
    sample_rate = 16000
    frames = bytearray()
    for index in range(int(duration_s * sample_rate)):
        sample = int(1000 * math.sin(2 * math.pi * 220 * index / sample_rate))
        frames.extend(sample.to_bytes(2, "little", signed=True))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(frames)
    return buffer.getvalue()


def _request_output(text: str, finished: bool) -> RequestOutput:
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
                finish_reason="stop" if finished else None,
            )
        ],
        finished=finished,
    )


def _generator(parts: tuple[str, ...]) -> AsyncGenerator[RequestOutput, None]:
    async def generate():
        for index, part in enumerate(parts):
            yield _request_output(part, finished=index == len(parts) - 1)

    return generate()


def _parse_sse(lines: list[str]) -> tuple[str, list[dict], bool]:
    contents = []
    objects = []
    done = False
    for line in "".join(lines).splitlines():
        if not line.startswith("data: "):
            continue
        payload = line.removeprefix("data: ").strip()
        if payload == "[DONE]":
            done = True
            continue
        item = json.loads(payload)
        objects.append(item)
        for choice in item.get("choices") or []:
            content = (choice.get("delta") or {}).get("content")
            if content is not None:
                contents.append(content)
    return "".join(contents), objects, done


async def run_public_speech_request(
    api: str,
    stream: bool,
    language: str | None,
    chunks: list[tuple[str, ...]],
    to_language: str | None = None,
    model_cls: type[StubTranscriptionModel] = StubTranscriptionModel,
) -> SpeechResult:
    outputs = iter(chunks)
    renderer = StubRenderer()
    engine = MagicMock()
    engine.model_config = MagicMock()
    engine.model_config.get_diff_sampling_param.return_value = {
        "max_tokens": 256,
        "temperature": 0.0,
    }
    engine.model_config.is_encoder_decoder = False
    engine.model_config.model = "stub-model"
    engine.model_config.max_model_len = 8192
    engine.errored = False
    engine.renderer = renderer
    engine.input_processor = MagicMock()
    engine.generate.side_effect = lambda *_args, **_kwargs: _generator(next(outputs))
    models = MagicMock(spec=OpenAIServingModels)
    models.lora_requests = {}
    models.is_base_model.return_value = True

    with patch(
        "vllm.model_executor.model_loader.get_model_cls",
        return_value=model_cls,
    ):
        if api == "transcription":
            serving = OpenAIServingTranscription(engine, models, request_logger=None)
            request = TranscriptionRequest.model_construct(
                file=MagicMock(),
                model="stub-model",
                language=language,
                stream=stream,
                response_format="json",
            )
            response = await serving.create_transcription(
                make_wav(len(chunks)), request, raw_request=None
            )
        elif api == "translation":
            serving = OpenAIServingTranslation(engine, models, request_logger=None)
            request = TranslationRequest.model_construct(
                file=MagicMock(),
                model="stub-model",
                language=language,
                to_language=to_language,
                stream=stream,
                response_format="json",
            )
            response = await serving.create_translation(
                make_wav(len(chunks)), request, raw_request=None
            )
        else:
            raise ValueError(api)

    assert engine.generate.call_count == len(chunks)
    assert renderer.prompt_count == len(chunks)
    assert not isinstance(response, ErrorResponse)
    if stream:
        lines = [line async for line in response]
        text, objects, done = _parse_sse(lines)
        return SpeechResult(text, engine.generate.call_count, renderer.prompt_count, objects, done)
    return SpeechResult(
        response.text,
        engine.generate.call_count,
        renderer.prompt_count,
        [],
        False,
    )
