from __future__ import annotations

from itertools import product

import pytest

from verifier_support import PARSERS, argument, multiple_wire, run_probe, wire


MODES = ("complete", "stream")
PARSER_MODES = tuple(product(PARSERS, MODES))


@pytest.mark.parametrize("parser", PARSERS)
def test_literal_entities_are_preserved_complete(parser: str) -> None:
    value = "Tom &amp; Jerry &lt;3 &quot;quoted&quot; &apos;apostrophe&apos;"
    result = run_probe(parser, "complete", wire(parser, [("content", value)]))
    assert argument(result)["content"] == value


@pytest.mark.parametrize("parser", PARSERS)
def test_literal_entities_are_preserved_streaming(parser: str) -> None:
    value = "A &amp; B &lt; C &gt; D &amp;amp;"
    result = run_probe(parser, "stream", wire(parser, [("content", value)]))
    assert argument(result)["content"] == value


@pytest.mark.parametrize(
    ("parser", "mode"),
    PARSER_MODES,
    ids=[f"{parser}-{mode}" for parser, mode in PARSER_MODES],
)
def test_numeric_entities_are_preserved_complete_and_streaming(
    parser: str,
    mode: str,
) -> None:
    value = "A &#38; B &#x3C; C &#X3E; D &#00038; E &#128512;"
    result = run_probe(parser, mode, wire(parser, [("content", value)]))
    assert argument(result)["content"] == value


@pytest.mark.parametrize("parser", PARSERS)
def test_escaped_closing_delimiters_remain_escaped(parser: str) -> None:
    values = {
        "minimax_m2": "x &lt;/parameter&gt;&lt;/invoke&gt;",
        "qwen_coder": "x &lt;/parameter&gt;&lt;/function&gt;",
        "glm_xml": "x &lt;/arg_value&gt;&lt;/tool_call&gt;",
        "deepseek_dsml": "x &lt;/｜DSML｜parameter&gt;&lt;/｜DSML｜invoke&gt;",
    }
    result = run_probe(parser, "complete", wire(parser, [("content", values[parser])]))
    assert argument(result)["content"] == values[parser]


@pytest.mark.parametrize("parser", PARSERS)
def test_numeric_and_structured_values_keep_schema_conversion(parser: str) -> None:
    parameters = [
        ("content", "raw &amp; text"),
        ("count", "5"),
        ("flag", "true"),
        ("payload", '{"nested":true}'),
        ("items", "[1,2]"),
        ("empty", "null"),
    ]
    result = run_probe(parser, "complete", wire(parser, parameters))
    assert argument(result) == {
        "content": "raw &amp; text",
        "count": 5,
        "flag": True,
        "payload": {"nested": True},
        "items": [1, 2],
        "empty": None,
    }


@pytest.mark.parametrize("parser", PARSERS)
def test_typed_values_work_with_streaming_boundaries(parser: str) -> None:
    parameters = [
        ("content", "stream &lt;value&gt;"),
        ("count", "9"),
        ("flag", "false"),
    ]
    result = run_probe(parser, "stream", wire(parser, parameters))
    args = argument(result)
    assert args["content"] == "stream &lt;value&gt;"
    assert args["count"] == 9
    assert args["flag"] is False


@pytest.mark.parametrize("parser", PARSERS)
def test_unknown_and_incomplete_entities_are_unchanged(parser: str) -> None:
    value = "Tom &unknown; Jerry &amp and &#notanumber; and &#xZZ;"
    result = run_probe(parser, "complete", wire(parser, [("content", value)]))
    assert argument(result)["content"] == value


@pytest.mark.parametrize("parser", PARSERS)
def test_plain_assistant_text_is_preserved(parser: str) -> None:
    result = run_probe(parser, "complete", "ordinary assistant text")
    assert result["normal_text"] == "ordinary assistant text"
    assert result["calls"] == []


@pytest.mark.parametrize("parser", PARSERS)
def test_multiple_tool_calls_keep_order(parser: str) -> None:
    text = multiple_wire(parser, ["first &amp;", "second &lt;"])
    result = run_probe(parser, "stream", text)
    assert [call["index"] for call in result["calls"]] == [0, 1]
    assert [call["arguments"]["content"] for call in result["calls"]] == [
        "first &amp;",
        "second &lt;",
    ]


@pytest.mark.parametrize("parser", PARSERS)
def test_incomplete_tool_call_reports_an_error(parser: str) -> None:
    text = wire(parser, [("content", "unfinished")])
    result = run_probe(parser, "stream", text[:-8])
    assert "error" in result


@pytest.mark.parametrize("parser", PARSERS)
def test_ordinary_strings_without_entities_are_unchanged(parser: str) -> None:
    value = "plain UTF-8 杭州 Paris"
    result = run_probe(parser, "complete", wire(parser, [("content", value)]))
    assert argument(result)["content"] == value


@pytest.mark.parametrize(
    ("parser", "mode"),
    PARSER_MODES,
    ids=[f"{parser}-{mode}" for parser, mode in PARSER_MODES],
)
def test_existing_whitespace_normalization_is_unchanged(
    parser: str,
    mode: str,
) -> None:
    cases = {
        "minimax_m2": ("  padded text  ", "  padded text  "),
        "qwen_coder": ("\n  padded text  \n", "  padded text  "),
        "glm_xml": ("  padded text  ", "padded text"),
        "deepseek_dsml": ("  padded text  ", "  padded text  "),
    }
    value, expected = cases[parser]
    result = run_probe(parser, mode, wire(parser, [("content", value)]))
    assert argument(result)["content"] == expected
