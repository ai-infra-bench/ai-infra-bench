from __future__ import annotations

import json

from verifier_support import assert_bound_tcp_endpoints, run_scenario


def main() -> int:
    race = run_scenario("race", servers=3)

    ipc = run_scenario("ipc", servers=2)

    crash = run_scenario("crash", servers=2)

    slow = run_scenario("slow", servers=2, delay=0.8, ready_timeout=6)

    print(
        json.dumps(
            {
                "entrypoint": "run_multi_api_server with real spawned MPClient children and ZMQ sockets",
                "race": {key: race[key] for key in ("status", "inputs", "outputs")},
                "ipc": {key: ipc[key] for key in ("status", "inputs", "outputs")},
                "crash": {
                    key: crash[key]
                    for key in ("status", "error_type", "error", "elapsed_seconds")
                },
                "slow": {
                    key: slow[key]
                    for key in ("status", "elapsed_seconds", "inputs", "outputs")
                },
            },
            separators=(",", ":"),
        )
    )
    assert_bound_tcp_endpoints(race, 3)
    assert ipc["status"] == "ok"
    assert all(
        endpoint.startswith("ipc://")
        for endpoint in [*ipc["inputs"], *ipc["outputs"]]
    )
    assert crash["status"] == "error"
    assert crash["elapsed_seconds"] < 3.0
    assert_bound_tcp_endpoints(slow, 2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
