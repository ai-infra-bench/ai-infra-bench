from __future__ import annotations

from verifier_support import PARSERS, argument, multiple_wire, run_probe, wire


def test_literal_entities_are_preserved_complete() -> None:
    value = "Tom &amp; Jerry &lt;3 &quot;quoted&quot;"
    for parser in PARSERS:
        result = run_probe(parser, "complete", wire(parser, [("content", value)]))
        assert argument(result)["content"] == value


def test_literal_entities_are_preserved_streaming() -> None:
    value = "A &amp; B &lt; C &gt; D"
    for parser in PARSERS:
        result = run_probe(parser, "stream", wire(parser, [("content", value)]))
        assert argument(result)["content"] == value


def test_escaped_closing_delimiters_remain_escaped() -> None:
    values = {
        "minimax_m2": "x &lt;/parameter&gt;&lt;/invoke&gt;",
        "qwen_coder": "x &lt;/parameter&gt;&lt;/function&gt;",
        "glm_xml": "x &lt;/arg_value&gt;&lt;/tool_call&gt;",
        "deepseek_dsml": "x &lt;/｜DSML｜parameter&gt;&lt;/｜DSML｜invoke&gt;",
    }
    for parser, value in values.items():
        result = run_probe(parser, "complete", wire(parser, [("content", value)]))
        assert argument(result)["content"] == value


def test_numeric_and_structured_values_keep_schema_conversion() -> None:
    parameters = [
        ("content", "raw &amp; text"),
        ("count", "5"),
        ("flag", "true"),
        ("payload", '{"nested":true}'),
        ("items", "[1,2]"),
        ("empty", "null"),
    ]
    for parser in PARSERS:
        result = run_probe(parser, "complete", wire(parser, parameters))
        args = argument(result)
        assert args == {
            "content": "raw &amp; text",
            "count": 5,
            "flag": True,
            "payload": {"nested": True},
            "items": [1, 2],
            "empty": None,
        }


def test_typed_values_work_with_streaming_boundaries() -> None:
    parameters = [
        ("content", "stream &lt;value&gt;"),
        ("count", "9"),
        ("flag", "false"),
    ]
    for parser in PARSERS:
        result = run_probe(parser, "stream", wire(parser, parameters))
        args = argument(result)
        assert args["content"] == "stream &lt;value&gt;"
        assert args["count"] == 9
        assert args["flag"] is False


def test_unknown_and_incomplete_entities_are_unchanged() -> None:
    value = "Tom &unknown; Jerry &amp and &#notanumber;"
    for parser in PARSERS:
        result = run_probe(parser, "complete", wire(parser, [("content", value)]))
        assert argument(result)["content"] == value


def test_plain_assistant_text_is_preserved() -> None:
    for parser in PARSERS:
        result = run_probe(parser, "complete", "ordinary assistant text")
        assert result["normal_text"] == "ordinary assistant text"
        assert result["calls"] == []


def test_multiple_tool_calls_keep_order() -> None:
    for parser in PARSERS:
        text = multiple_wire(parser, ["first &amp;", "second &lt;"])
        result = run_probe(parser, "stream", text)
        assert [call["index"] for call in result["calls"]] == [0, 1]
        assert [call["arguments"]["content"] for call in result["calls"]] == [
            "first &amp;",
            "second &lt;",
        ]


def test_incomplete_tool_call_reports_an_error() -> None:
    for parser in PARSERS:
        text = wire(parser, [("content", "unfinished")])
        result = run_probe(parser, "stream", text[:-8])
        assert "error" in result


def test_ordinary_strings_without_entities_are_unchanged() -> None:
    value = "plain UTF-8 杭州 Paris"
    for parser in PARSERS:
        result = run_probe(parser, "complete", wire(parser, [("content", value)]))
        assert argument(result)["content"] == value
