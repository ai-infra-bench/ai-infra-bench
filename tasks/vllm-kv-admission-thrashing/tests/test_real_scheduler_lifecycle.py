#!/usr/bin/env python3
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scheduler_probe import ContentionCase, run_contention_case

def main() -> int:
    cases = [ContentionCase(13, 16, 32, 96, 112),
             ContentionCase(7, 32, 32, 96, 128),
             ContentionCase(18, 16, 48, 128, 160)]
    results = []
    for index, case in enumerate(cases):
        result = run_contention_case(
            Path(tempfile.mkdtemp(prefix=f"kv-lifecycle-{index}-")), case)
        results.append({"case": case.__dict__, "result": result})
    print(json.dumps({"scheduler_lifecycle": results}), flush=True)
    assert all(item["result"]["target_preemptions"] <= 1 for item in results)
    assert all(item["result"]["rollback_events"] <= 1 for item in results)
    assert all(item["result"]["incumbent_finished"] for item in results)
    assert all(item["result"]["target_finished"] for item in results)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
