import json

import pytest

from ai_infra_bench.rq1.model_labeler import (
    LabelingConfig,
    ModelLabeler,
    _parse_json,
    _user_prompt,
)


def test_prompt_contains_paths_but_not_unbounded_file_list() -> None:
    record = {
        "source_id": "vllm__pr__123",
        "title": "Fix scheduler",
        "files": [{"path": f"path/{index}"} for index in range(4)],
    }

    prompt = _user_prompt([record], max_files=2)
    payload = json.loads(prompt.split("\n", 1)[1])

    assert payload[0]["files"] == ["path/0", "path/1"]
    assert payload[0]["files_truncated_or_unavailable"] is True


def test_prompt_marks_explicitly_unavailable_file_evidence() -> None:
    record = {
        "source_id": "vllm__pr__456",
        "title": "Fix API behavior",
        "files": [],
        "file_paths_unavailable": True,
    }

    prompt = _user_prompt([record], max_files=2)
    payload = json.loads(prompt.split("\n", 1)[1])

    assert payload[0]["files_truncated_or_unavailable"] is True


def test_parse_json_accepts_fenced_model_output() -> None:
    assert _parse_json("```json\n{\"items\": []}\n```") == {"items": []}


def test_parse_json_rejects_non_object() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        _parse_json("[]")


def test_concurrency_per_key_must_be_positive() -> None:
    with pytest.raises(ValueError, match="concurrency_per_key"):
        LabelingConfig(concurrency_per_key=0)


def test_model_labeler_requires_explicit_gateway(monkeypatch) -> None:
    monkeypatch.delenv("AIB_MODEL_ENDPOINT", raising=False)
    with pytest.raises(ValueError, match="AIB_MODEL_ENDPOINT"):
        ModelLabeler(["test-key"], LabelingConfig())


def test_model_client_uses_configured_gateway(monkeypatch) -> None:
    monkeypatch.setenv("AIB_MODEL_ENDPOINT", "https://gateway.example.test")
    labeler = ModelLabeler(["test-key"], LabelingConfig())
    client = labeler._client(0)
    try:
        assert str(client.base_url) == "https://gateway.example.test/openai/"
        assert not any(
            name.lower().startswith("x-tt-") for name in client.default_headers
        )
    finally:
        client.close()
