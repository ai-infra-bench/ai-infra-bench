"""Record current-suite results and exact input hashes from real run artifacts."""

from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    task = Path(__file__).resolve().parents[2]
    previous = json.loads(
        (task / "validation/history/f4163bc/latest_python/results.json").read_text()
    )
    inventory = json.loads((task / "validation/case-inventory.json").read_text())
    frozen = json.loads((args.artifacts / "frozen-test-hashes.json").read_text())
    assert all(sha(task / name) == digest for name, digest in frozen.items())
    xml = ET.parse(args.artifacts / "python-current.xml").getroot()
    counts = {
        key: sum(int(s.get(key, "0")) for s in xml.iter("testsuite"))
        for key in ("tests", "failures", "errors", "skipped")
    }
    assert counts["tests"] == inventory["total_pytest_cases"]
    assert counts["errors"] == counts["skipped"] == 0
    by_file = defaultdict(lambda: {"passed": 0, "failed": 0})
    cases = []
    for case in xml.iter("testcase"):
        failure = case.find("failure")
        status = "failed" if failure is not None else "passed"
        by_file[case.get("classname")][status] += 1
        row = {
            "name": case.get("name"),
            "file_group": case.get("classname"),
            "result": status,
        }
        if failure is not None:
            row["failure_message"] = failure.get("message", "")[:1600]
            row["failure_trace_sha256"] = hashlib.sha256(
                (failure.text or "").encode()
            ).hexdigest()
        cases.append(row)
    assert len({(row["file_group"], row["name"]) for row in cases}) == counts["tests"]
    for group in inventory["groups"]:
        assert sum(by_file[Path(group["file"]).stem].values()) == group["cases"]
    controls = json.loads((args.artifacts / "python-cpu-control.log").read_text())
    assert len(controls["checks"]) == 10 and all(controls["checks"].values())
    fixture_count = sum(by_file["test_sdk_fixture"].values())
    native_count = sum(by_file["test_real_qwen_backend"].values()) + sum(
        row["name"] == "test_existing_rust_openai_and_health_routes" for row in cases
    )
    summary = {
        **counts,
        "passed": counts["tests"] - counts["failures"],
        "pytest_exit_code": int(counts["failures"] > 0),
        "sdk_fixture": by_file["test_sdk_fixture"],
        "server_cases": {
            "passed": counts["tests"] - counts["failures"] - fixture_count,
            "failed": counts["failures"],
        },
        "anthropic_behavior_cases": {
            "passed": counts["tests"]
            - counts["failures"]
            - fixture_count
            - native_count,
            "failed": counts["failures"],
        },
        "existing_api_backend_controls": {"passed": native_count, "failed": 0},
    }
    assert (
        summary["passed"] == inventory["total_pytest_cases"] and counts["failures"] == 0
    )
    record = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "reference": json.loads(
            (args.artifacts / "reference-manifest.json").read_text()
        ),
        "benchmark": {
            "parent_commit": previous["benchmark"]["commit"],
            "revision_identity": "Verifier hardening working tree; exact scored test hashes below identify the executed revision.",
            "base_commit": previous["benchmark"]["base_commit"],
            "canonical_image_id": previous["benchmark"]["canonical_image_id"],
            "test_file_sha256": frozen,
            "instruction_sha256": sha(task / "instruction.md"),
        },
        "boundary": previous["boundary"],
        "summary": summary,
        "by_file": dict(by_file),
        "real_cpu_controls": {
            "passed": 10,
            "failed": 0,
            "exit_code": 0,
            "shm_size": "1g",
            "checks": controls["checks"],
        },
        "artifact_hashes": {
            name: sha(args.artifacts / name)
            for name in (
                "python-current.xml",
                "python-current.log",
                "python-cpu-control.log",
            )
        },
        "adapter_hashes": {
            name: sha(Path(__file__).with_name(name))
            for name in (
                "adapter.py",
                "server.py",
                "pytest_plugin.py",
                "run.sh",
                "record_results.py",
            )
        },
        "artifact_directory": str(args.artifacts),
        "cases": cases,
        "limitations": [
            "No complete Rust implementation or Oracle pass is established.",
            "The reference is the immutable main commit resolved on 2026-09-05, not a moving latest claim.",
            "EngineCore generation and transport are replaced. Actual GPU/model compute and EngineCore IPC are outside this comparison; the separate ten-control run executes real CPU dummy weights.",
            "Strict response validation exposes malformed events that default SDK parsing can tolerate. The task explicitly requires protocol-valid output.",
            "A failing Python result alone is neither a reason to retain a test nor proof of an independent product bug.",
        ],
    }
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
