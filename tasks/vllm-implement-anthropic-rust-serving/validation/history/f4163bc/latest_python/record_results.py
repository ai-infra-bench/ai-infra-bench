"""Build a per-case evidence record from the actual reference run artifacts."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    task = Path(__file__).resolve().parents[2]
    xml = ET.parse(args.artifacts / "latest-python.xml").getroot()
    counts = {
        key: sum(int(s.get(key, "0")) for s in xml.iter("testsuite"))
        for key in ("tests", "failures", "errors", "skipped")
    }
    assert counts == {"tests": 115, "failures": 20, "errors": 0, "skipped": 0}, counts
    by_file = defaultdict(lambda: {"passed": 0, "failed": 0})
    cases = []
    failed_number = 0
    drop_variants = {
        "search_result_input",
        "server_tool_use_history",
        "web_search_result_history",
        "web_fetch_and_code_execution_results",
        "bash_and_text_editor_results",
        "tool_search_and_container_upload",
    }
    rewrite_cases = {
        "test_reasoning_then_text_stream",
        "test_anthropic_validation_error_envelope",
        "test_request_variant_reaches_rust_semantic_path[tool_result_tool_reference]",
        "test_request_variant_reaches_rust_semantic_path[custom_tool_all_fields]",
    }
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
            failed_number += 1
            row["failure_number"] = failed_number
            row["failure_message"] = failure.get("message", "")[:1600]
            row["failure_trace_sha256"] = hashlib.sha256(
                (failure.text or "").encode()
            ).hexdigest()
            variant = row["name"].split("[")[-1].removesuffix("]")
            row["recommendation"] = (
                "remove_success_requirement"
                if variant in drop_variants
                else "rewrite_or_merge"
                if row["name"] in rewrite_cases
                else "retain_behavior"
            )
            row["explanation"] = f"failures.md section {failed_number:02}"
        cases.append(row)
    assert len({row["name"] for row in cases}) == 115
    assert failed_number == 20
    source = json.loads((args.artifacts / "reference-source-hashes.json").read_text())
    frozen = json.loads((task / "validation/e2e-evidence.json").read_text())[
        "artifacts"
    ]["test_file_sha256"]
    assert all(sha(task / name) == digest for name, digest in frozen.items())
    controls = json.loads(
        (args.artifacts / "latest-python-basic-control-retry.log").read_text()
    )
    assert len(controls["checks"]) == 10 and all(controls["checks"].values())
    record = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "reference": {
            "source_commit": "e962733e08d10f7ca65dac4df99e116460b8b174",
            "selected_ref": "main",
            "sdk": "anthropic==1.3.0",
            "torch": "2.13.0+cpu",
            "image": "ai-infra-bench/reference-python-anthropic:main-e962733e08d1",
            "image_id": "sha256:fd803711169b26d1a40d0d0dea108912b5457b74bf4c12f44f8ba3e5254adc59",
            "source_archive_sha256": sha(args.artifacts / "vllm.tar.gz"),
            "dockerfile_sha256": sha(args.artifacts / "Dockerfile.reference"),
            "installed_packages_sha256": sha(args.artifacts / "installed-packages.txt"),
            "source_files_verified_against_archive": source,
        },
        "benchmark": {
            "commit": "f4163bcf3166fd1799341d0bbc5defa8afea65b5",
            "base_commit": "e196268bade5291c3fd80906bf9cd8c64851b21b",
            "canonical_image_id": "sha256:535bb97cac5f23043e7874dfde5037c1fee6d76d180d1da2e6e8217ca161d125",
            "scored_files_unchanged": True,
            "test_file_sha256": frozen,
        },
        "boundary": "Latest real vllm serve Python application, AsyncLLM input/output processors, Qwen renderer/tokenizer, tool/reasoning parsers, HTTP/SSE and official SDK. EngineCore generation/transport alone is replaced by scripted token outputs.",
        "summary": {
            **counts,
            "passed": 95,
            "pytest_exit_code": 1,
            "server_cases": {"passed": 60, "failed": 20},
            "anthropic_behavior_cases": {"passed": 52, "failed": 20},
            "sdk_fixture": {"passed": 35, "failed": 0},
            "existing_api_backend_controls": {"passed": 8, "failed": 0},
        },
        "by_file": dict(by_file),
        "recommendation_counts": dict(
            Counter(row["recommendation"] for row in cases if row["result"] == "failed")
        ),
        "real_cpu_controls": {
            "passed": 10,
            "failed": 0,
            "exit_code": 0,
            "shm_size": "1g",
            "checks": controls["checks"],
            "initial_setup_note": "The initial 64 MiB /dev/shm attempt failed before serving; the worker requested 160 MiB. Rerun with 1 GiB succeeded. This setup failure is not counted as an API failure.",
        },
        "artifact_hashes": {
            name: sha(args.artifacts / name)
            for name in (
                "latest-python.xml",
                "latest-python.log",
                "failure-details.json",
                "negative-responses.json",
                "latest-python-basic-control.log",
                "latest-python-basic-control-retry.log",
            )
        },
        "adapter_hashes": {
            name: sha(Path(__file__).with_name(name))
            for name in (
                "adapter.py",
                "server.py",
                "pytest_plugin.py",
                "probe_details.py",
                "probe_negative_requests.py",
            )
        },
        "supplementary_details": "failure-details.json; raw negative-response replays are retained in the artifact directory",
        "artifact_directory": str(args.artifacts),
        "cases": cases,
        "limitations": [
            "No complete Rust implementation or Oracle pass is established.",
            "No scored case was removed or weakened in this audit; recommendations require an explicit final contract.",
            "Strict-response validation is deliberately enabled; some malformed error envelopes still produce a status-based SDK exception.",
            "This comparison does not execute real GPU/model generation or EngineCore IPC; the separate ten-control run does execute a CPU model with dummy weights.",
        ],
    }
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "summary": record["summary"],
                "recommendations": record["recommendation_counts"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
