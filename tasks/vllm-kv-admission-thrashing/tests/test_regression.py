import pytest

from scheduler_probe import (
    ContentionCase,
    run_burst_case,
    run_contention_case,
    run_prefix_case,
)


THRASHING_CASES = [
    ContentionCase(13, 16, 32, 96, 112),
    ContentionCase(10, 16, 24, 64, 96),
    ContentionCase(7, 32, 32, 96, 128),
    ContentionCase(18, 16, 48, 128, 160),
]


@pytest.mark.parametrize("case", THRASHING_CASES)
def test_contention_completes_without_recomputation(tmp_path, case):
    result = run_contention_case(tmp_path, case)
    assert result["target_preemptions"] <= 1
    assert result["request_preemption_count"] <= 1
    assert result["rollback_events"] <= 1
    assert result["incumbent_progress"] == sorted(result["incumbent_progress"])
    assert result["incumbent_finished"] is True
    assert result["target_finished"] is True
    assert result["steps"] < 64


@pytest.mark.parametrize("case,target_prompts", [
    (ContentionCase(20, 16, 48, 96, 160), (160, 144)),
    (ContentionCase(22, 16, 64, 96, 160), (160, 160, 144)),
])
def test_burst_of_long_prompts_does_not_repeat_preemption(
        tmp_path, case, target_prompts):
    result = run_burst_case(tmp_path, case, target_prompts)
    assert result["incumbent_finished"] is True
    assert all(result["targets_finished"])
    assert max(result["target_preemptions"]) <= 1
    assert max(result["rollback_events"]) <= 1
    assert result["steps"] < 128


FITTING_CASES = [
    ContentionCase(13, 16, 32, 96, 80),
    ContentionCase(12, 16, 24, 80, 64),
    ContentionCase(8, 32, 32, 96, 96),
]


@pytest.mark.parametrize("case", FITTING_CASES)
def test_request_that_fits_is_not_unnecessarily_serialized(tmp_path, case):
    result = run_contention_case(tmp_path, case)
    assert result["target_progress_while_incumbent_active"] is True
    assert result["target_finished"] is True


@pytest.mark.parametrize("params", [
    {"num_blocks": 13, "block_size": 16, "batch_tokens": 32,
     "seed_tokens": 64, "target_tokens": 160},
    {"num_blocks": 25, "block_size": 8, "batch_tokens": 24,
     "seed_tokens": 80, "target_tokens": 176},
])
def test_prefix_cache_credit_remains_usable(tmp_path, params):
    result = run_prefix_case(tmp_path, **params)
    assert result["first_scheduled"] > 0
    assert result["cached_tokens"] > 0
    assert result["target_preemptions"] <= 1
    assert result["target_finished"] is True


@pytest.mark.parametrize("attention_kind,num_blocks", [
    ("sliding", 13),
    ("chunked_local", 12),
    ("hybrid", 30),
])
def test_recycling_attention_keeps_existing_concurrency(
        tmp_path, attention_kind, num_blocks):
    result = run_contention_case(
        tmp_path,
        ContentionCase(num_blocks, 16, 32, 64, 192),
        attention_kind=attention_kind,
        attention_window=64,
    )
    assert result["target_progress_while_incumbent_active"] is True
    assert result["target_preemptions"] <= 1
    assert result["rollback_events"] <= 1
    assert result["incumbent_finished"] is True
    assert result["target_finished"] is True
