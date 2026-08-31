#!/usr/bin/env python3
"""Exercise public speech APIs with real WAV decoding and audio splitting."""

from __future__ import annotations

import asyncio

from speech_harness import run_public_speech_request


async def run():
    transcription = await run_public_speech_request(
        "transcription",
        True,
        "en",
        [
            ("A founding member",),
            ("of OpenAI",),
            ("joined", " the server"),
        ],
    )
    translation = await run_public_speech_request(
        "translation",
        False,
        "zh",
        [("The service",), ("is healthy",)],
    )
    chinese = await run_public_speech_request(
        "translation",
        True,
        "en",
        [("你好",), ("世界",)],
        to_language="zh",
    )
    assert transcription.text == "A founding member of OpenAI joined the server"
    assert translation.text == "The service is healthy"
    assert chinese.text == "你好世界"
    assert transcription.done is True
    assert chinese.done is True
    assert transcription.engine_calls == transcription.prompt_count == 3
    assert translation.engine_calls == translation.prompt_count == 2
    assert chinese.engine_calls == chinese.prompt_count == 2
    print(
        {
            "entrypoints": [
                "OpenAIServingTranscription.create_transcription",
                "OpenAIServingTranslation.create_translation",
            ],
            "real_wav_decode_and_split": True,
            "streaming_transcription": transcription.text,
            "nonstreaming_translation": translation.text,
            "streaming_chinese_translation": chinese.text,
            "audio_chunks": [3, 2, 2],
        },
        flush=True,
    )


def main() -> int:
    try:
        asyncio.run(run())
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
