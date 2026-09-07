"""Independent compatibility cases outside the grading inventory."""

from verifier_support import PARSERS, argument, run_probe, wire


CASES = {
    "minimax_m2": (
        "prefix &amp; &#60;/parameter&#x3E; "
        "&lt;/invoke&#62; &amp;lt;/parameter&amp;gt;",
        "prefix &amp; </parameter> </invoke> &amp;lt;/parameter&amp;gt;",
    ),
    "qwen_coder": (
        "prefix &amp; &#x3C;/parameter&#62; "
        "&lt;/function&#x3E; &amp;lt;/tool_call&amp;gt;",
        "prefix &amp; </parameter> </function> &amp;lt;/tool_call&amp;gt;",
    ),
    "glm_xml": (
        "prefix &amp; &#60;/arg_value&#62; "
        "&lt;/tool_call&#x3E; &amp;lt;/arg_value&amp;gt;",
        "prefix &amp; </arg_value> </tool_call> &amp;lt;/arg_value&amp;gt;",
    ),
    "deepseek_dsml": (
        "prefix &amp; &#x3C;/｜DSML｜parameter&#62; "
        "&lt;/｜DSML｜invoke&#x3E; &amp;lt;/｜DSML｜parameter&amp;gt;",
        "prefix &amp; </｜DSML｜parameter> </｜DSML｜invoke> "
        "&amp;lt;/｜DSML｜parameter&amp;gt;",
    ),
}


def main() -> None:
    results = []
    for parser in PARSERS:
        value, expected = CASES[parser]
        for mode in ("complete", "stream"):
            result = run_probe(
                parser,
                mode,
                wire(parser, [("content", value)]),
                chunk_sizes=[1, 2, 5, 3] * 256 if mode == "stream" else None,
            )
            actual = argument(result)["content"]
            results.append({
                "parser": parser,
                "mode": mode,
                "actual": actual,
                "expected": expected,
                "passed": actual == expected,
            })
    assert len(results) == 8 and all(row["passed"] for row in results), results
    print({"independent_compatibility_cases": len(results), "passed": 8})


if __name__ == "__main__":
    main()
