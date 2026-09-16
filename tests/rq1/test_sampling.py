from ai_infra_bench.rq1.sampling import (
    backend_keyword_sample,
    patch_size,
    period,
    stratified_sample,
)


def record(number: int, merged_at: str, churn: int) -> dict:
    return {
        "number": number,
        "merged_at": merged_at,
        "additions": churn,
        "deletions": 0,
        "source_id": f"vllm__pr__{number}",
        "title": "Generic change",
        "files": [],
    }


def test_period_and_patch_size_follow_frozen_boundaries() -> None:
    assert period(record(1, "2024-12-31T00:00:00Z", 20)) == (
        "launch_through_2024"
    )
    assert period(record(2, "2025-01-01T00:00:00Z", 21)) == "2025"
    assert patch_size(record(1, "2024-01-01T00:00:00Z", 20)) == "small"
    assert patch_size(record(2, "2025-01-01T00:00:00Z", 21)) == "medium"
    assert patch_size(record(3, "2026-01-01T00:00:00Z", 201)) == "large"
    assert patch_size({"additions": None, "deletions": None}) == "unknown"
    assert period({"created_at": "2025-03-01T00:00:00Z"}) == "2025"


def test_stratified_sample_is_repeatable_and_covers_groups() -> None:
    records = [
        record(1, "2024-01-01T00:00:00Z", 10),
        record(2, "2024-01-01T00:00:00Z", 100),
        record(3, "2025-01-01T00:00:00Z", 10),
        record(4, "2025-01-01T00:00:00Z", 100),
        record(5, "2026-01-01T00:00:00Z", 10),
        record(6, "2026-01-01T00:00:00Z", 100),
    ]

    first = stratified_sample(records, count=6, seed=7)
    second = stratified_sample(records, count=6, seed=7)

    assert first == second
    assert {item["sample"]["period"] for item in first} == {
        "launch_through_2024",
        "2025",
        "2026",
    }


def test_backend_sample_includes_all_rare_matches_without_treating_as_truth() -> None:
    records = [
        dict(record(1, "2026-01-01T00:00:00Z", 1), title="Ascend fix"),
        dict(record(2, "2026-01-01T00:00:00Z", 1), title="MLU docs"),
        dict(record(3, "2026-01-01T00:00:00Z", 1), title="Generic fix"),
    ]

    result = backend_keyword_sample(records, per_backend=10, seed=7)

    assert [item["number"] for item in result] == [1, 2]
    assert result[0]["sample"]["matched_backend_hints"] == ["ascend_npu"]
