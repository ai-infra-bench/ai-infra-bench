from __future__ import annotations

import argparse
import json
import os


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["race", "baseline", "ipc", "rust", "crash", "slow"])
    parser.add_argument("--servers", type=int, default=4)
    parser.add_argument("--delay", type=float, default=0.0)
    parser.add_argument("--ready-timeout", type=int)
    args = parser.parse_args()
    if args.ready_timeout is not None:
        os.environ["VLLM_ENGINE_READY_TIMEOUT_S"] = str(args.ready_timeout)

    from port_harness import run_scenario

    mode = "baseline" if args.mode == "slow" else args.mode
    result = run_scenario(mode, servers=args.servers, worker_delay=args.delay)
    result["requested_mode"] = args.mode
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
