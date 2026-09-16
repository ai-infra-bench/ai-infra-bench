from ai_infra_bench.rq1.pr_review_metrics import _review_rounds


def _review(timestamp: str) -> dict:
    return {"submittedAt": timestamp}


def _commit(timestamp: str) -> dict:
    return {
        "commit": {
            "pushedDate": timestamp,
            "committedDate": timestamp,
        }
    }


def test_review_rounds_require_revision_between_reviews() -> None:
    reviews = [
        _review("2026-01-01T01:00:00Z"),
        _review("2026-01-01T02:00:00Z"),
        _review("2026-01-01T04:00:00Z"),
    ]
    commits = [_commit("2026-01-01T03:00:00Z")]

    assert _review_rounds(reviews, commits) == 2


def test_review_rounds_are_zero_without_review() -> None:
    assert _review_rounds([], [_commit("2026-01-01T03:00:00Z")]) == 0
