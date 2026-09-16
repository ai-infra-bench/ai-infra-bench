import json
from pathlib import Path

from ai_infra_bench.rq1.git_manifest import (
    extract_pr_number,
    input_hash,
    strip_pr_suffix,
    write_manifest,
)


def test_extracts_only_trailing_pr_number() -> None:
    assert extract_pr_number("Fix scheduler (#123)") == 123
    assert extract_pr_number("Mention #123 without squash suffix") is None
    assert strip_pr_suffix("Fix scheduler (#123)") == "Fix scheduler"


def test_input_hash_ignores_non_classification_metadata() -> None:
    record = {
        "source_id": "vllm__pr__123",
        "title": "Fix scheduler",
        "files": [{"path": "vllm/core/scheduler.py", "additions": 1}],
        "merged_at": "2026-01-01T00:00:00Z",
    }
    changed = dict(record, merged_at="2026-02-01T00:00:00Z")

    assert input_hash(record) == input_hash(changed)


def test_manifest_is_written_in_pr_number_order(tmp_path: Path) -> None:
    output = tmp_path / "manifest.jsonl"
    write_manifest(iter([{"number": 2}, {"number": 1}]), output)

    values = [json.loads(line) for line in output.read_text().splitlines()]
    assert [value["number"] for value in values] == [1, 2]
