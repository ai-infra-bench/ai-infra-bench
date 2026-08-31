from collections import deque
from unittest.mock import patch

import pytest
from transformers import PretrainedConfig

from vllm.transformers_utils import config as config_module


class SequenceParser:
    def __init__(self, outcomes) -> None:
        self.outcomes = deque(outcomes)
        self.calls = 0

    def parse(self, *args, **kwargs):
        self.calls += 1
        outcome = self.outcomes.popleft()
        if isinstance(outcome, BaseException):
            raise outcome
        return {}, outcome


def _get_config(tmp_path, parser):
    (tmp_path / "config.json").write_text('{"model_type":"bert"}')
    with (
        patch.object(config_module, "get_config_parser", return_value=parser),
        patch("vllm.transformers_utils.repo_utils.time.sleep", return_value=None),
    ):
        return config_module.get_config(
            tmp_path,
            trust_remote_code=False,
            config_format="hf",
        )


@pytest.mark.parametrize(
    "transient_error",
    [
        FileNotFoundError("config.json temporarily unavailable"),
        ValueError("config.json temporarily empty or malformed"),
    ],
)
def test_transient_parse_failure_recovers(tmp_path, transient_error) -> None:
    expected = PretrainedConfig(architectures=["BertModel"])
    parser = SequenceParser([transient_error, expected])

    config = _get_config(tmp_path, parser)

    assert parser.calls == 2
    assert config.architectures == ["BertModel"]


def test_valid_config_is_not_retried(tmp_path) -> None:
    expected = PretrainedConfig(architectures=["BertModel"])
    parser = SequenceParser([expected])

    config = _get_config(tmp_path, parser)

    assert parser.calls == 1
    assert config.architectures == ["BertModel"]


@pytest.mark.parametrize(
    "persistent_error",
    [
        FileNotFoundError("config.json is missing"),
        ValueError("config.json is malformed"),
    ],
)
def test_persistent_parse_failure_remains_an_error(tmp_path, persistent_error) -> None:
    parser = SequenceParser(
        [
            type(persistent_error)(str(persistent_error)),
            type(persistent_error)(str(persistent_error)),
        ]
    )

    with pytest.raises(type(persistent_error), match=str(persistent_error)):
        _get_config(tmp_path, parser)

    assert parser.calls == 2
