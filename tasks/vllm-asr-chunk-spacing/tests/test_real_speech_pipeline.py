#!/usr/bin/env python3
"""Exercise both public streaming speech endpoints across audio chunks."""

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/tests")

import test_regression as suite


async def run():
    transcription = await suite._stream(
        suite.OpenAIServingTranscription,
        "transcription_stream_generator",
        "en",
        [("A founding member",), ("of OpenAI",), ("joined", " the server")],
    )
    translation = await suite._stream(
        suite.OpenAIServingTranslation,
        "translation_stream_generator",
        "zh",
        [("你好",), ("世界",)],
    )
    assert transcription == "A founding member of OpenAI joined the server"
    assert translation == "你好世界"
    print(
        {
            "entrypoints": [
                "OpenAIServingTranscription.transcription_stream_generator",
                "OpenAIServingTranslation.translation_stream_generator",
            ],
            "english": transcription,
            "chinese": translation,
            "audio_chunks": [3, 2],
        },
        flush=True,
    )


def main() -> int:
    try:
        asyncio.run(run())
        return 0
    except Exception as exc:
        lines = str(exc).splitlines()
        print({"error": type(exc).__name__, "message": lines[0] if lines else "no exception message"}, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
