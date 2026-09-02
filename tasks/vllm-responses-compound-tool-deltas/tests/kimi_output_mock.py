from __future__ import annotations

import json


EXPECTED_BASH_ARGUMENTS = {
    "command": (
        "cd /testbed && git status --short && "
        "sed -n '220,280p' astropy/modeling/separable.py && "
        "rg -n '_cstack|separability_matrix|compound_models' "
        "astropy/modeling/separable.py astropy/modeling/tests/test_separable.py && "
        "python -m pytest astropy/modeling/tests/test_separable.py -q"
    )
}


def kimi_tool_chunks(
    name: str,
    index: int,
    arguments: dict,
    *,
    width: int = 61,
    leading_content: str = "",
) -> list[str]:
    payload = json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))
    fragments = [payload[start : start + width] for start in range(0, len(payload), width)]
    fragments[0] = (
        leading_content
        + "<|tool_calls_section_begin|>"
        f"<|tool_call_begin|>functions.{name}:{index}"
        "<|tool_call_argument_begin|>"
        + fragments[0]
    )
    fragments.append("<|tool_call_end|>")
    return fragments


def separated_kimi_tool_chunks(
    name: str,
    index: int,
    argument_text: str,
) -> list[str]:
    return [
        (
            "<|tool_calls_section_begin|>"
            f"<|tool_call_begin|>functions.{name}:{index}"
            "<|tool_call_argument_begin|>"
        ),
        argument_text + "<|tool_call_end|>",
    ]


BASH_TOOL_CHUNKS = kimi_tool_chunks("bash", 0, EXPECTED_BASH_ARGUMENTS)


HIDDEN_BASH_ARGUMENTS = {
    "command": (
        "cd /testbed && sed -n '55,105p' astropy/timeseries/core.py && "
        "rg -n '_check_required_columns|required_columns' "
        "astropy/timeseries/core.py astropy/timeseries/tests/test_sampled.py && "
        "python -m pytest astropy/timeseries/tests/test_sampled.py -q"
    )
}
HIDDEN_BASH_TOOL_CHUNKS = kimi_tool_chunks(
    "bash",
    0,
    HIDDEN_BASH_ARGUMENTS,
    width=43,
)


PARALLEL_BASH_ARGUMENTS = [
    {
        "command": (
            "cd /testbed && sed -n '220,280p' astropy/modeling/separable.py && "
            "git log -5 --oneline -- astropy/modeling/separable.py"
        )
    },
    {
        "command": (
            "cd /testbed && "
            "python -m pytest astropy/modeling/tests/test_separable.py -q"
        )
    },
]


_FIRST_PARALLEL_ARGUMENTS = json.dumps(
    PARALLEL_BASH_ARGUMENTS[0], separators=(",", ":")
)
_SECOND_PARALLEL_ARGUMENTS = json.dumps(
    PARALLEL_BASH_ARGUMENTS[1], separators=(",", ":")
)
PARALLEL_TOOL_CHUNKS = [
    (
        "<|tool_calls_section_begin|>"
        "<|tool_call_begin|>functions.bash:0"
        "<|tool_call_argument_begin|>"
        + _FIRST_PARALLEL_ARGUMENTS[:47]
    ),
    _FIRST_PARALLEL_ARGUMENTS[47:94],
    (
        _FIRST_PARALLEL_ARGUMENTS[94:]
        + "<|tool_call_end|>"
        "<|tool_call_begin|>functions.bash:1"
        "<|tool_call_argument_begin|>"
        + _SECOND_PARALLEL_ARGUMENTS[:31]
    ),
    _SECOND_PARALLEL_ARGUMENTS[31:] + "<|tool_call_end|>",
]
