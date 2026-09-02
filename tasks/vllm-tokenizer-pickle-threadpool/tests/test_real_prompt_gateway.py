from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="prompt-gateway-verifier-") as raw_dir:
        output = Path(raw_dir) / "batch-plan.json"
        completed = subprocess.run(
            ["python", "main.py", "--output", str(output)],
            cwd="/workspace/prompt-gateway",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=300,
            check=False,
        )
        if completed.returncode != 0:
            print(completed.stdout)
            raise AssertionError(f"prompt gateway exited {completed.returncode}")
        report = json.loads(output.read_text(encoding="utf-8"))
        assert report["counters"]["received"] == 3
        assert report["counters"]["accepted"] == 3
        assert report["counters"]["rejected"] == 0
        assert report["batches"]
        assert all(item["input_token_ids"] for item in report["accepted"])
        print(
            json.dumps(
                {
                    "entrypoint": "task-owned Ray prompt gateway",
                    "received": report["counters"]["received"],
                    "accepted": report["counters"]["accepted"],
                    "batches": len(report["batches"]),
                },
                separators=(",", ":"),
            )
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
