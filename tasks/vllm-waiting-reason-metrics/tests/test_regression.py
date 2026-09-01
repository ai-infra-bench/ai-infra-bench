from __future__ import annotations

import logging

from vllm.v1.metrics.loggers import (
    AggregatedLoggingStatLogger,
    LoggingStatLogger,
)

from verifier_support import (
    metric_value,
    prometheus_output,
    scheduled_request_ids,
    scheduler_stats,
)


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def capture_log(logger) -> str:
    target = logging.getLogger("vllm.v1.metrics.loggers")
    handler = _Capture()
    previous_level = target.level
    target.setLevel(logging.INFO)
    target.addHandler(handler)
    try:
        logger.log()
    finally:
        target.removeHandler(handler)
        target.setLevel(previous_level)
    return "\n".join(handler.messages)


def test_prometheus_exposes_capacity_and_deferred(tmp_path) -> None:
    text = prometheus_output(tmp_path, [(1, 2)])
    assert metric_value(
        text,
        "vllm:num_requests_waiting_by_reason",
        engine=0,
        reason="capacity",
    ) == 1
    assert metric_value(
        text,
        "vllm:num_requests_waiting_by_reason",
        engine=0,
        reason="deferred",
    ) == 2


def test_existing_total_equals_reason_sum(tmp_path) -> None:
    text = prometheus_output(tmp_path, [(3, 4)])
    total = metric_value(text, "vllm:num_requests_waiting", engine=0)
    capacity = metric_value(
        text,
        "vllm:num_requests_waiting_by_reason",
        engine=0,
        reason="capacity",
    )
    deferred = metric_value(
        text,
        "vllm:num_requests_waiting_by_reason",
        engine=0,
        reason="deferred",
    )
    assert total == capacity + deferred == 7


def test_zero_reason_series_are_present(tmp_path) -> None:
    text = prometheus_output(tmp_path, [(0, 2), (3, 0)])
    assert metric_value(
        text,
        "vllm:num_requests_waiting_by_reason",
        engine=0,
        reason="capacity",
    ) == 0
    assert metric_value(
        text,
        "vllm:num_requests_waiting_by_reason",
        engine=1,
        reason="deferred",
    ) == 0


def test_each_engine_keeps_its_own_breakdown(tmp_path) -> None:
    text = prometheus_output(tmp_path, [(1, 2), (4, 1)])
    assert metric_value(text, "vllm:num_requests_waiting", engine=0) == 3
    assert metric_value(text, "vllm:num_requests_waiting", engine=1) == 5
    assert metric_value(
        text,
        "vllm:num_requests_waiting_by_reason",
        engine=1,
        reason="capacity",
    ) == 4


def test_log_reports_total_and_nonzero_deferred(tmp_path) -> None:
    stats, config = scheduler_stats(tmp_path, capacity=2, deferred=3)
    logger = LoggingStatLogger(config)
    logger.record(stats, None)
    logger.num_prompt_tokens = 1
    message = capture_log(logger)
    assert "Waiting: 5 reqs" in message
    assert "Deferred: 3 reqs" in message


def test_log_omits_deferred_when_zero(tmp_path) -> None:
    stats, config = scheduler_stats(tmp_path, capacity=2, deferred=0)
    logger = LoggingStatLogger(config)
    logger.record(stats, None)
    logger.num_prompt_tokens = 1
    message = capture_log(logger)
    assert "Waiting: 2 reqs" in message
    assert "Deferred:" not in message


def test_aggregated_log_sums_both_populations(tmp_path) -> None:
    first, config = scheduler_stats(tmp_path / "one", capacity=1, deferred=2)
    second, _ = scheduler_stats(tmp_path / "two", capacity=3, deferred=1)
    logger = AggregatedLoggingStatLogger(config, engine_indexes=[0, 1])
    logger.record(first, None, engine_idx=0)
    logger.record(second, None, engine_idx=1)
    logger.num_prompt_tokens = 1
    message = capture_log(logger)
    assert "Waiting: 7 reqs" in message
    assert "Deferred: 3 reqs" in message


def test_existing_running_and_cache_metrics_remain(tmp_path) -> None:
    text = prometheus_output(tmp_path, [(1, 1)])
    assert "vllm:num_requests_running{" in text
    assert "vllm:kv_cache_usage_perc{" in text


def test_observability_change_preserves_fcfs_scheduling(tmp_path) -> None:
    assert scheduled_request_ids(tmp_path) == ["capacity-0", "capacity-1"]
