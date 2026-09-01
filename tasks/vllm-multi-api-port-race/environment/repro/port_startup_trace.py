from __future__ import annotations

import json

from port_harness import run_scenario


def main() -> int:
    attempts = [run_scenario("race", servers=4) for _ in range(4)]
    print(json.dumps(attempts, indent=2))
    passed = all(
        item["status"] == "ok"
        and len(item["ports"]) == 8
        and all(port > 0 for port in item["ports"])
        and len(set(item["ports"])) == 8
        for item in attempts
    )
    print(f"multi_api_startup_contract={passed}")
    return 0 if passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
