from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from opencode_provider import (
    EDIT_ERROR,
    OpenCodeProvider,
    text_chunks,
    tool_chunks,
    tool_definitions,
)
from verifier_support import PARSERS, argument, run_probe, wire


MODEL_IDS = {
    "minimax_m2": "MiniMaxAI/MiniMax-M2.5",
    "qwen_coder": "Qwen/Qwen3-Coder-480B-A35B-Instruct",
    "glm_xml": "zai-org/GLM-4.5",
    "deepseek_dsml": "deepseek-ai/DeepSeek-V3.2",
}

STORY_OLD = (
    "<central.search.url>https://search.maven.org/solrsearch/select?"
    "q=g%3Aorg.junit.jupiter&amp;rows=20&amp;wt=json</central.search.url>"
)
STORY_NEW = STORY_OLD.replace("rows=20", "rows=100")
STORY_PROMPTS = (
    "Change the Maven Central query limit from 20 to 100. I need a higher limit.",
    "? You have to read the file before you edit it. Read it again and retry "
    "with the exact oldString that's actually there.",
    "It failed again. Seriously, what are you even changing?? Show me the "
    "exact oldString you used.",
)

ENTITY_SPELLINGS = (
    "&amp;",
    "&lt;",
    "&gt;",
    "&quot;",
    "&apos;",
    "&#38;",
    "&#60;",
    "&#62;",
    "&#34;",
    "&#39;",
    "&#128512;",
    "&#x26;",
    "&#x3C;",
    "&#x3E;",
    "&#x22;",
    "&#x27;",
    "&#x1F600;",
    "&#X3E;",
    "&#00038;",
    "&unknown;",
    "&amp",
    "&#xZZ;",
)
ENTITY_PAYLOAD = "|".join(ENTITY_SPELLINGS)
MATRIX_OLD = f"<entity.probe><![CDATA[{ENTITY_PAYLOAD}|limit=20]]></entity.probe>"
MATRIX_NEW = MATRIX_OLD.replace("limit=20", "limit=100")

STREAM_CHUNKS = {
    "minimax_m2": [1, 7, 2, 13, 3, 5] * 256,
    "qwen_coder": [9, 1, 4, 2, 11, 3] * 256,
    "glm_xml": [2, 8, 1, 15, 4, 3] * 256,
    "deepseek_dsml": [3, 1, 12, 2, 6, 5] * 256,
}


def _pom(property_line: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>org.aiinfrabench</groupId>
  <artifactId>maven-central-search-client</artifactId>
  <version>1.0.0</version>
  <properties>
    {property_line}
  </properties>
</project>
"""


def _config(port: int, model_id: str) -> str:
    return json.dumps(
        {
            "$schema": "https://opencode.ai/config.json",
            "model": f"vllm-local/{model_id}",
            "provider": {
                "vllm-local": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "Local vLLM endpoint",
                    "options": {
                        "baseURL": f"http://127.0.0.1:{port}/v1",
                        "apiKey": "local-verifier-token",
                    },
                    "models": {model_id: {"name": model_id}},
                }
            },
            "permission": {"read": "allow", "edit": "allow"},
        },
        indent=2,
    )


def _events(output: str) -> list[dict]:
    return [json.loads(line) for line in output.splitlines() if line.startswith("{")]


def _tool_result(payload: dict) -> str:
    return str(payload.get("messages", [])[-1].get("content", ""))


def _tool_schema(payload: dict, name: str) -> tuple[list[dict], set[str]]:
    definitions = tool_definitions(payload)
    definition = next(item for item in definitions if item["name"] == name)
    properties = definition["parameters"].get("properties", {})
    string_parameters = {
        key for key, schema in properties.items() if schema.get("type") == "string"
    }
    return definitions, string_parameters


def _parsed_tool_call(
    payload: dict,
    parser: str,
    mode: str,
    name: str,
    parameters: list[tuple[str, str]],
) -> dict:
    definitions, string_parameters = _tool_schema(payload, name)
    parsed = run_probe(
        parser,
        mode,
        wire(
            parser,
            parameters,
            tool_name=name,
            string_parameters=string_parameters,
        ),
        tools=definitions,
        chunk_sizes=STREAM_CHUNKS[parser] if mode == "stream" else None,
    )
    assert len(parsed["calls"]) == 1, parsed
    assert parsed["calls"][0]["name"] == name, parsed
    return argument(parsed)


def _parsed_text(parser: str, mode: str, content: str) -> str:
    parsed = run_probe(
        parser,
        mode,
        content,
        chunk_sizes=STREAM_CHUNKS[parser] if mode == "stream" else None,
    )
    assert parsed["calls"] == [], parsed
    return parsed["normal_text"]


def _environment(root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    for name in ("config", "data", "cache", "state"):
        location = root / "xdg" / name
        location.mkdir(parents=True)
        environment[f"XDG_{name.upper()}_HOME"] = str(location)
    environment.update({"CI": "true", "NO_COLOR": "1"})
    return environment


def _run_opencode(
    project: Path,
    environment: dict[str, str],
    arguments: list[str],
) -> list[dict]:
    completed = subprocess.run(
        [
            "/usr/local/bin/opencode",
            "run",
            "--pure",
            "--format",
            "json",
            "--dir",
            str(project),
            *arguments,
        ],
        cwd=project,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        env=environment,
        check=False,
    )
    assert completed.returncode == 0, {
        "arguments": arguments,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "returncode": completed.returncode,
    }
    events = _events(completed.stdout)
    assert events, completed
    return events


def _tool_events(events: list[dict], name: str) -> list[dict]:
    return [
        event
        for event in events
        if event.get("type") == "tool_use" and event["part"]["tool"] == name
    ]


def _maven_validate(pom: Path) -> int:
    return subprocess.run(
        ["mvn", "--offline", "--quiet", "-f", str(pom), "validate"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    ).returncode


def run_story() -> dict:
    parser = "minimax_m2"
    mode = "stream"
    model_id = MODEL_IDS[parser]
    with tempfile.TemporaryDirectory(prefix="opencode-story-") as raw_root:
        root = Path(raw_root)
        project = root / "maven-search-client"
        project.mkdir()
        pom = project / "pom.xml"
        original = _pom(STORY_OLD)
        pom.write_text(original)
        stage = "first-edit"
        read_observed = False

        def respond(payload: dict) -> list[dict]:
            nonlocal stage, read_observed
            if stage == "first-edit":
                parsed = _parsed_tool_call(
                    payload,
                    parser,
                    mode,
                    "edit",
                    [
                        ("filePath", str(pom)),
                        ("oldString", STORY_OLD),
                        ("newString", STORY_NEW),
                    ],
                )
                stage = "first-result"
                return tool_chunks(payload, "edit", parsed)
            if stage == "first-result":
                result = _tool_result(payload)
                if "Edit applied successfully." in result:
                    stage = "done"
                    return text_chunks(payload, "Updated the Maven Central query limit.")
                assert EDIT_ERROR in result, result
                stage = "second-read"
                return text_chunks(payload, "The edit failed because oldString was not found.")
            if stage == "second-read":
                parsed = _parsed_tool_call(
                    payload,
                    parser,
                    mode,
                    "read",
                    [("filePath", str(pom))],
                )
                stage = "second-read-result"
                return tool_chunks(payload, "read", parsed)
            if stage == "second-read-result":
                result = _tool_result(payload)
                assert STORY_OLD in result, result
                read_observed = True
                parsed = _parsed_tool_call(
                    payload,
                    parser,
                    mode,
                    "edit",
                    [
                        ("filePath", str(pom)),
                        ("oldString", STORY_OLD),
                        ("newString", STORY_NEW),
                    ],
                )
                stage = "second-edit-result"
                return tool_chunks(payload, "edit", parsed)
            if stage == "second-edit-result":
                result = _tool_result(payload)
                assert EDIT_ERROR in result, result
                stage = "third-text"
                return text_chunks(payload, "The edit still failed because oldString was not found.")
            if stage == "third-text":
                text = (
                    "I used this exact oldString:\n"
                    f"```xml\n{STORY_OLD}\n```"
                )
                stage = "done"
                return text_chunks(payload, _parsed_text(parser, mode, text))
            raise AssertionError(f"unexpected provider stage: {stage}")

        with OpenCodeProvider(respond) as provider:
            (project / "opencode.json").write_text(_config(provider.port, model_id))
            environment = _environment(root)
            first = _run_opencode(
                project,
                environment,
                ["--model", f"vllm-local/{model_id}", STORY_PROMPTS[0]],
            )
            first_edits = _tool_events(first, "edit")
            assert len(first_edits) == 1, first
            first_status = first_edits[0]["part"]["state"]["status"]
            runs = [first]
            if first_status == "error":
                runs.append(
                    _run_opencode(project, environment, ["--continue", STORY_PROMPTS[1]])
                )
                runs.append(
                    _run_opencode(project, environment, ["--continue", STORY_PROMPTS[2]])
                )
            assert not provider.errors, provider.errors

        session_ids = {
            event["sessionID"]
            for events in runs
            for event in events
            if "sessionID" in event
        }
        edit_events = [event for events in runs for event in _tool_events(events, "edit")]
        read_events = [event for events in runs for event in _tool_events(events, "read")]
        text = "\n".join(
            event["part"]["text"]
            for events in runs
            for event in events
            if event.get("type") == "text"
        )
        content = pom.read_text()
        edit_inputs = [event["part"]["state"]["input"] for event in edit_events]
        edit_succeeded = (
            len(edit_events) == 1
            and edit_events[0]["part"]["state"]["status"] == "completed"
            and STORY_NEW in content
            and STORY_OLD not in content
            and edit_inputs[0]["oldString"] == STORY_OLD
            and edit_inputs[0]["newString"] == STORY_NEW
            and _maven_validate(pom) == 0
        )
        base_failure_observed = (
            len(runs) == 3
            and len(session_ids) == 1
            and len(edit_events) == 2
            and all(event["part"]["state"]["status"] == "error" for event in edit_events)
            and all(EDIT_ERROR in event["part"]["state"]["error"] for event in edit_events)
            and all(
                item["oldString"] == STORY_OLD.replace("&amp;", "&")
                and item["newString"] == STORY_NEW.replace("&amp;", "&")
                for item in edit_inputs
            )
            and len(read_events) == 1
            and read_events[0]["part"]["state"]["status"] == "completed"
            and read_observed
            and STORY_OLD in text
            and content == original
            and _maven_validate(pom) == 0
        )
        assert stage == "done", stage
        assert edit_succeeded or base_failure_observed, {
            "runs": runs,
            "content": content,
            "stage": stage,
        }
        return {
            "parser": parser,
            "mode": mode,
            "model": model_id,
            "turns": len(runs),
            "single_session": len(session_ids) == 1,
            "edit_attempts": len(edit_events),
            "read_completed": len(read_events) == 1,
            "base_failure_observed": base_failure_observed,
            "edit_succeeded": edit_succeeded,
        }


def run_matrix_cell(parser: str, mode: str) -> dict:
    model_id = MODEL_IDS[parser]
    with tempfile.TemporaryDirectory(prefix=f"opencode-matrix-{parser}-{mode}-") as raw_root:
        root = Path(raw_root)
        project = root / "maven-search-client"
        project.mkdir()
        pom = project / "pom.xml"
        original = _pom(MATRIX_OLD)
        pom.write_text(original)
        stage = "edit"

        def respond(payload: dict) -> list[dict]:
            nonlocal stage
            if stage == "edit":
                parsed = _parsed_tool_call(
                    payload,
                    parser,
                    mode,
                    "edit",
                    [
                        ("filePath", str(pom)),
                        ("oldString", MATRIX_OLD),
                        ("newString", MATRIX_NEW),
                    ],
                )
                stage = "result"
                return tool_chunks(payload, "edit", parsed)
            result = _tool_result(payload)
            stage = "done"
            if "Edit applied successfully." in result:
                return text_chunks(payload, "Updated the entity probe limit.")
            assert EDIT_ERROR in result, result
            return text_chunks(payload, "The entity probe edit failed.")

        with OpenCodeProvider(respond) as provider:
            (project / "opencode.json").write_text(_config(provider.port, model_id))
            events = _run_opencode(
                project,
                _environment(root),
                [
                    "--model",
                    f"vllm-local/{model_id}",
                    "Change the entity probe limit in pom.xml from 20 to 100.",
                ],
            )
            request_tool_names = {
                item["name"]
                for request in provider.requests
                for item in tool_definitions(request)
            }
            assert not provider.errors, provider.errors

        edits = _tool_events(events, "edit")
        content = pom.read_text()
        edit_input = edits[0]["part"]["state"]["input"] if len(edits) == 1 else {}
        succeeded = (
            len(edits) == 1
            and edits[0]["part"]["state"]["status"] == "completed"
            and MATRIX_NEW in content
            and MATRIX_OLD not in content
            and edit_input.get("oldString") == MATRIX_OLD
            and edit_input.get("newString") == MATRIX_NEW
            and all(entity in content for entity in ENTITY_SPELLINGS)
            and _maven_validate(pom) == 0
        )
        failed_as_expected = (
            len(edits) == 1
            and edits[0]["part"]["state"]["status"] == "error"
            and EDIT_ERROR in edits[0]["part"]["state"]["error"]
            and edit_input.get("oldString") != MATRIX_OLD
            and content == original
            and _maven_validate(pom) == 0
        )
        assert stage == "done", stage
        assert succeeded or failed_as_expected, {"events": events, "content": content}
        return {
            "parser": parser,
            "mode": mode,
            "model": model_id,
            "actual_edit_schema": "edit" in request_tool_names,
            "entity_spellings": len(ENTITY_SPELLINGS),
            "edit_succeeded": succeeded,
            "base_failure_observed": failed_as_expected,
        }


def main() -> int:
    story = run_story()
    matrix = [
        run_matrix_cell(parser, mode)
        for parser in PARSERS
        for mode in ("complete", "stream")
    ]
    opencode_version = subprocess.run(
        ["/usr/local/bin/opencode", "--version"],
        text=True,
        stdout=subprocess.PIPE,
        check=True,
    ).stdout.strip()
    assert opencode_version == "1.17.3", opencode_version
    print(
        json.dumps(
            {
                "entrypoint": (
                    "real OpenCode request schema -> production Rust ToolParser -> "
                    "OpenAI-compatible SSE -> real OpenCode read/edit -> pom.xml -> Maven"
                ),
                "model_boundary": "deterministic responses mounted only with tests",
                "opencode_version": opencode_version,
                "story": story,
                "matrix": matrix,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    assert story["edit_succeeded"], story
    assert all(result["actual_edit_schema"] for result in matrix), matrix
    assert all(result["edit_succeeded"] for result in matrix), matrix
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
