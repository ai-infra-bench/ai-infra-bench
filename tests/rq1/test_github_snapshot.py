import pytest

from ai_infra_bench.rq1.github_snapshot import (
    ISSUE_QUERY,
    PULL_REQUEST_QUERY,
    _split_repository,
)


def test_base_queries_request_ordered_census_and_activity_counts() -> None:
    assert "orderBy: {field: CREATED_AT, direction: ASC}" in ISSUE_QUERY
    assert "comments { totalCount }" in ISSUE_QUERY
    assert "reviews { totalCount }" in PULL_REQUEST_QUERY
    assert "reviewThreads { totalCount }" in PULL_REQUEST_QUERY
    assert "additions deletions changedFiles" in PULL_REQUEST_QUERY


def test_repository_must_have_owner_and_name() -> None:
    assert _split_repository("vllm-project/vllm") == (
        "vllm-project",
        "vllm",
    )
    with pytest.raises(ValueError, match="owner/name"):
        _split_repository("vllm")
