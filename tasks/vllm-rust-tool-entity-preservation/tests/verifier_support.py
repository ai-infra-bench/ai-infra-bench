from __future__ import annotations

import json
import os
import subprocess


PARSERS = ("minimax_m2", "qwen_coder", "glm_xml", "deepseek_dsml")


def wire(parser: str, parameters: list[tuple[str, str]]) -> str:
    if parser == "minimax_m2":
        values = "".join(
            f'<parameter name="{name}">{value}</parameter>'
            for name, value in parameters
        )
        return (
            '<minimax:tool_call><invoke name="write_file">'
            f"{values}</invoke></minimax:tool_call>"
        )
    if parser == "qwen_coder":
        values = "\n".join(
            f"<parameter={name}>{value}</parameter>"
            for name, value in parameters
        )
        return (
            "<tool_call>\n<function=write_file>\n"
            f"{values}\n</function>\n</tool_call>"
        )
    if parser == "glm_xml":
        values = "\n".join(
            f"<arg_key>{name}</arg_key>\n<arg_value>{value}</arg_value>"
            for name, value in parameters
        )
        return f"<tool_call>write_file\n{values}\n</tool_call>"
    if parser == "deepseek_dsml":
        values = "\n".join(
            (
                f'<｜DSML｜parameter name="{name}" '
                f'string="{"true" if name == "content" else "false"}">'
                f"{value}</｜DSML｜parameter>"
            )
            for name, value in parameters
        )
        return (
            '<｜DSML｜function_calls>\n<｜DSML｜invoke name="write_file">\n'
            f"{values}\n</｜DSML｜invoke>\n</｜DSML｜function_calls>"
        )
    raise AssertionError(parser)


def multiple_wire(parser: str, values: list[str]) -> str:
    if parser == "minimax_m2":
        invokes = "".join(
            '<invoke name="write_file">'
            f'<parameter name="content">{value}</parameter>'
            "</invoke>"
            for value in values
        )
        return f"<minimax:tool_call>{invokes}</minimax:tool_call>"
    if parser == "deepseek_dsml":
        invokes = "\n".join(
            '<｜DSML｜invoke name="write_file">'
            f'<｜DSML｜parameter name="content" string="true">{value}'
            "</｜DSML｜parameter></｜DSML｜invoke>"
            for value in values
        )
        return f"<｜DSML｜function_calls>{invokes}</｜DSML｜function_calls>"
    return "".join(wire(parser, [("content", value)]) for value in values)


def run_probe(parser: str, mode: str, text: str) -> dict:
    executable = os.environ["AI_INFRA_TOOL_PROBE"]
    result = subprocess.run(
        [executable, parser, mode, text],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=True,
    )
    return json.loads(result.stdout.splitlines()[-1])


def argument(result: dict, index: int = 0) -> dict:
    return result["calls"][index]["arguments"]
