#!/usr/bin/env python3
"""Exercise real Docker cleanup after cancellation and a stale container."""

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from gpu_pool import Pool, POOL_LABEL, GPU_LABEL


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    pool = Pool(Path(os.environ["AI_INFRA_GPU_POOL_CONFIG"]))
    prefix = [sys.executable, str(SCRIPTS / "gpu_pool.py"), "--count", "1", "--"]
    labels = ["--label", f"{POOL_LABEL}={pool.identity}", "--label", f"{GPU_LABEL}0=true"]
    gpu = ["--gpus", f"device={pool.devices[0]}"]
    inspect = ["docker", "ps", "-aq", "--filter", f"label={POOL_LABEL}={pool.identity}"]
    if subprocess.check_output(inspect, text=True).strip():
        raise RuntimeError("run this smoke test only when the CI pool is idle")
    with (args.output / "cancel.log").open("w") as log:
        supervisor = subprocess.Popen(
            [*prefix, "docker", "run", "--rm", "--network=none", *labels, *gpu, args.image, "sleep", "90"],
            stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 30
            while not subprocess.check_output([*inspect, "--filter", "status=running"], text=True).strip():
                if supervisor.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("cancel smoke container did not start")
                time.sleep(0.1)
            supervisor.send_signal(signal.SIGTERM)
            if supervisor.wait(timeout=40) != 143:
                raise RuntimeError("unexpected cancellation exit code")
        finally:
            if supervisor.poll() is None:
                supervisor.send_signal(signal.SIGTERM)
                supervisor.wait(timeout=40)
    assert not subprocess.check_output(inspect, text=True).strip(), "cancellation leaked a container"
    with pool.acquire(4, timeout=1):
        pass

    stale = subprocess.check_output(
        ["docker", "run", "-d", "--network=none", *labels, *gpu, args.image, "sleep", "90"], text=True,
    ).strip()
    try:
        with (args.output / "recovery.log").open("w") as log:
            subprocess.run([*prefix, "true"], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=40)
        assert not subprocess.check_output(inspect, text=True).strip(), "stale container was not reclaimed"
    finally:
        subprocess.run(["docker", "rm", "-f", stale], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    result = {"cancellation": "passed", "stale_container_recovery": "passed", "all_gpu_locks_reusable": True}
    (args.output / "evidence.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
