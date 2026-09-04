import pytest

from speech_harness import StubQwen3Model, run_public_speech_request


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "api,stream,language,to_language,chunks,expected",
    [
        (
            "transcription",
            True,
            "en",
            None,
            [("Hello, this",), ("is vLLM",)],
            "Hello, this is vLLM",
        ),
        (
            "transcription",
            False,
            "en",
            None,
            [("superstar.",), ("A founding member",)],
            "superstar. A founding member",
        ),
        (
            "transcription",
            True,
            None,
            None,
            [("one",), ("two",), ("three",)],
            "one two three",
        ),
        (
            "transcription",
            False,
            "zh",
            None,
            [("你好",), ("世界",)],
            "你好世界",
        ),
        (
            "transcription",
            True,
            "ja",
            None,
            [("こん",), ("にちは",)],
            "こんにちは",
        ),
        (
            "translation",
            True,
            "zh",
            None,
            [("A founding member",), ("of OpenAI",)],
            "A founding member of OpenAI",
        ),
        (
            "translation",
            False,
            "ja",
            None,
            [("server.",), ("But I guess",)],
            "server. But I guess",
        ),
        (
            "translation",
            True,
            "en",
            "zh",
            [("你好",), ("世界",)],
            "你好世界",
        ),
        (
            "translation",
            False,
            "en",
            "ja",
            [("こん",), ("にちは",)],
            "こんにちは",
        ),
        (
            "translation",
            False,
            "en",
            None,
            [("mode.",), ("Putting this on",)],
            "mode. Putting this on",
        ),
    ],
    ids=[
        "stream-transcription-example",
        "nonstream-transcription-punctuation",
        "stream-transcription-language-unset",
        "nonstream-transcription-chinese",
        "stream-transcription-japanese",
        "stream-translation-default-english",
        "nonstream-translation-default-english",
        "stream-translation-chinese-target",
        "nonstream-translation-japanese-target",
        "nonstream-translation-punctuation",
    ],
)
async def test_public_multichunk_speech_behavior(
    api, stream, language, to_language, chunks, expected
):
    result = await run_public_speech_request(
        api, stream, language, chunks, to_language=to_language
    )

    assert result.text == expected
    if stream:
        assert result.done is True
        assert result.sse_objects
        expected_object = (
            "transcription.chunk" if api == "transcription" else "translation.chunk"
        )
        assert all(item["object"] == expected_object for item in result.sse_objects)


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["transcription", "translation"])
async def test_qwen3_nonstreaming_structured_chunks_preserve_word_boundaries(api):
    result = await run_public_speech_request(
        api,
        False,
        "en",
        [
            ("language English<asr_text>boundary",),
            ("language English<asr_text>spacing",),
        ],
        model_cls=StubQwen3Model,
    )

    assert result.text == "boundary spacing"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "api,stream",
    [
        ("transcription", True),
        ("transcription", False),
        ("translation", True),
        ("translation", False),
    ],
)
async def test_existing_leading_whitespace_is_not_duplicated(api, stream):
    result = await run_public_speech_request(
        api,
        stream,
        "en",
        [("Hello",), (" world",)],
    )

    assert result.text == "Hello world"


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "nonstream"])
async def test_existing_trailing_whitespace_is_not_duplicated(stream):
    result = await run_public_speech_request(
        "transcription",
        stream,
        "en",
        [("Hello ",), ("world",)],
    )

    assert result.text == "Hello world"


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["transcription", "translation"])
async def test_streaming_separator_is_added_once_per_audio_chunk(api):
    result = await run_public_speech_request(
        api,
        True,
        "en",
        [("hel", "lo"), ("wor", "ld")],
    )

    assert result.text == "hello world"


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["transcription", "translation"])
async def test_single_audio_chunk_has_no_leading_separator(api):
    result = await run_public_speech_request(
        api,
        True,
        "en",
        [("hello",)],
    )

    assert result.text == "hello"


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [True, False], ids=["stream", "nonstream"])
async def test_empty_model_delta_does_not_consume_chunk_boundary(stream):
    result = await run_public_speech_request(
        "transcription",
        stream,
        "en",
        [("hello",), ("", "world")],
    )

    assert result.text == "hello world"
