from __future__ import annotations

import pytest

from verifier_support import assert_bound_tcp_endpoints, run_scenario


@pytest.mark.parametrize("servers", [2, 4, 8])
def test_port_pressure_does_not_break_multi_server_startup(servers: int) -> None:
    assert_bound_tcp_endpoints(run_scenario("race", servers=servers), servers)


def test_one_server_startup_remains_usable() -> None:
    assert_bound_tcp_endpoints(run_scenario("baseline", servers=1), 1)


def test_unpressured_multi_server_startup_remains_usable() -> None:
    assert_bound_tcp_endpoints(run_scenario("baseline", servers=4), 4)


def test_ipc_endpoints_remain_supported() -> None:
    result = run_scenario("ipc", servers=3)
    assert result["status"] == "ok", result
    endpoints = [*result["inputs"], *result["outputs"]]
    assert len(endpoints) == 6
    assert len(set(endpoints)) == 6
    assert all(endpoint.startswith("ipc://") for endpoint in endpoints)


def test_frontend_without_report_back_keeps_concrete_addresses() -> None:
    result = run_scenario("rust", servers=1)
    assert_bound_tcp_endpoints(result, 1)


def test_child_exit_is_reported_without_hanging() -> None:
    result = run_scenario("crash", servers=3)
    assert result["status"] == "error", result
    assert result["elapsed_seconds"] < 3.0
    assert "ApiServer" in result["error"]
    assert "exit" in result["error"].lower() or "report" in result["error"].lower()


def test_configured_short_startup_timeout_is_honored() -> None:
    result = run_scenario("slow", servers=2, delay=2.0, ready_timeout=1)
    assert result["status"] == "error", result
    assert "Timed out" in result["error"]
    assert 0.8 <= result["elapsed_seconds"] < 3.0


def test_configured_longer_startup_timeout_allows_slow_workers() -> None:
    result = run_scenario("slow", servers=2, delay=1.2, ready_timeout=8)
    assert_bound_tcp_endpoints(result, 2)
    assert result["elapsed_seconds"] >= 1.0
