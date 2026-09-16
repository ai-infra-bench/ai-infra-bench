import json
import urllib.request

import pytest

from ai_infra_bench.rq1.github_snapshot import (
    GitHubGraphQLClient,
    GitHubRateLimitError,
)


class FakeResponse:
    headers = {"X-RateLimit-Reset": "12345"}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(
            {
                "data": None,
                "errors": [{"type": "RATE_LIMIT", "message": "exceeded"}],
            }
        ).encode()


def test_graphql_200_rate_limit_preserves_reset_timestamp(monkeypatch) -> None:
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(),
    )
    client = GitHubGraphQLClient(
        "token",
        max_attempts=1,
        wait_on_rate_limit=False,
    )

    with pytest.raises(RuntimeError) as captured:
        client.execute("query { viewer { login } }", {})

    assert isinstance(captured.value.__cause__, GitHubRateLimitError)
    assert captured.value.__cause__.reset_timestamp == 12345
