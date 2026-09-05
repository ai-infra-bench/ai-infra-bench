"""Validate final verifier-only runs and record their actual results.

Run outside the agent/verifier environment after the final executable snapshot
is frozen. In particular, reward zero alone cannot qualify native mutations or
the correct partial alternative while the Anthropic routes are absent.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text())


def junit(path: Path) -> dict:
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    counts = {
        key: sum(int(s.get(key, "0")) for s in root.iter("testsuite"))
        for key in ("tests", "failures", "errors", "skipped")
    }
    assert counts["tests"] == len(cases)
    assert counts["errors"] == counts["skipped"] == 0, path
    assert len({(c.get("classname"), c.get("name")) for c in cases}) == len(cases)
    failed = sorted(c.get("name") for c in cases if c.find("failure") is not None)
    passed = sorted(c.get("name") for c in cases if c.find("failure") is None)
    assert len(failed) == counts["failures"]
    native = [
        c
        for c in cases
        if c.get("name", "").startswith(("test_qwen_", "test_native_"))
        or c.get("name") == "test_existing_rust_openai_and_health_routes"
    ]
    return {
        **counts,
        "passed": len(passed),
        "failed_names": failed,
        "passed_names": passed,
        "native_passed": sorted(
            c.get("name") for c in native if c.find("failure") is None
        ),
        "native_failed": sorted(
            c.get("name") for c in native if c.find("failure") is not None
        ),
        "sha256": sha(path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    task = Path(__file__).resolve().parents[1]
    out = args.artifacts
    frozen = read_json(out / "frozen-inputs.json")
    assert all(sha(task / name) == digest for name, digest in frozen.items())
    inventory = read_json(task / "validation/case-inventory.json")
    fixture_count = next(
        g["cases"] for g in inventory["groups"] if g["file"] == "test_sdk_fixture.py"
    )
    native_count = 1 + next(
        g["cases"]
        for g in inventory["groups"]
        if g["file"] == "test_real_qwen_backend.py"
    )
    server_count = inventory["total_pytest_cases"] - fixture_count
    manifest = read_json(task / "validation/ci-cases.json")
    declared = {c["name"]: c for c in manifest["cases"]}
    trials, jobs = [], []
    for job_dir in sorted((out / "harbor-jobs").iterdir()):
        job_path = job_dir / "result.json"
        if not job_path.is_file():
            continue
        job = read_json(job_path)
        stats = job["stats"]
        assert stats["n_errored_trials"] == stats.get("n_cancelled_trials", 0) == 0
        assert stats["n_completed_trials"] == job["n_total_trials"]
        jobs.append(
            {
                "name": job_dir.name,
                "id": job["id"],
                "completed": stats["n_completed_trials"],
                "errored": 0,
                "result_sha256": sha(job_path),
            }
        )
        for result_path in sorted(job_dir.glob("*/result.json")):
            result = read_json(result_path)
            assert result["exception_info"] is None
            case_path = Path(result["task_id"]["path"])
            case_name = case_path.name
            assert case_name == "base" or case_name in declared
            for name, digest in frozen.items():
                if name.startswith("tests/") or name == "instruction.md":
                    assert sha(case_path / name) == digest, (case_name, name)
            logs = result_path.parent / "verifier"
            reward = read_json(logs / "reward.json")
            expected = (
                0 if case_name == "base" else declared[case_name]["expected_reward"]
            )
            assert reward["reward"] == expected
            assert all(
                reward[k] == 0
                for k in (
                    "inject_exit_code",
                    "compile_exit_code",
                    "sdk_fixture_exit_code",
                    "sdk_fixture_integrity_exit_code",
                    "python_control_exit_code",
                )
            )
            fixture, server = (
                junit(logs / "sdk_fixture.xml"),
                junit(logs / "rust_sdk_matrix.xml"),
            )
            assert fixture["tests"] == fixture["passed"] == fixture_count
            assert server["tests"] == server_count
            cpu = read_json(logs / "python_frontend_control.log")
            assert len(cpu["checks"]) == 10 and all(cpu["checks"].values())
            trials.append(
                {
                    "case": case_name,
                    "trial": result["trial_name"],
                    "trial_id": result["id"],
                    "job_id": job["id"],
                    "task_checksum": result["task_checksum"],
                    "task_path": str(case_path),
                    "reward": reward["reward"],
                    "reward_record": reward,
                    "fixture": fixture,
                    "server": server,
                    "result_sha256": sha(result_path),
                }
            )
    base = [t for t in trials if t["case"] == "base"]
    assert len(base) >= 3
    baseline_failures = base[0]["server"]["failed_names"]
    for trial in base:
        assert trial["server"]["passed"] == native_count
        assert len(trial["server"]["native_passed"]) == native_count
        assert trial["server"]["failed_names"] == baseline_failures
    controls = [t for t in trials if t["case"] != "base"]
    assert {t["case"] for t in controls} == set(declared)
    assert len(controls) == len(declared)
    for trial in controls:
        server, name = trial["server"], trial["case"]
        if name in (
            "static-json-endpoints",
            "count-tokens-only",
            "alternative-tool-none-normalization",
        ):
            assert server["failed_names"] == baseline_failures, name
            assert len(server["native_passed"]) == native_count, name
        elif name in ("ignore-generation-limit", "ignore-sampling-options"):
            rejected = [
                n
                for n in server["native_failed"]
                if n.startswith("test_native_generation_options_reach_engine[")
                and "chat/completions" in n
            ]
            assert len(rejected) == 4, (name, rejected)
        else:
            assert server["native_failed"], name
    python_reference = read_json(task / "validation/latest_python/results.json")
    assert python_reference["benchmark"]["test_file_sha256"] == {
        k: v for k, v in frozen.items() if k.startswith("tests/")
    }
    assert python_reference["summary"]["passed"] == inventory["total_pytest_cases"]
    alternative = junit(out / "python-alternative.xml")
    assert (
        alternative["tests"] == alternative["passed"] == inventory["total_pytest_cases"]
    )
    wrong_limit = junit(out / "python-ignore-limit.xml")
    assert wrong_limit["tests"] == wrong_limit["failures"] == 6
    assert all(
        n.startswith("test_sdk_generation_limit_reaches_engine_and_bounds_output[")
        for n in wrong_limit["failed_names"]
    )
    named_alternative = junit(out / "python-named-alternative.xml")
    assert named_alternative["tests"] == named_alternative["passed"] == 1
    response_variants = read_json(out / "response-variants.json")
    assert len(response_variants["cases"]) == 4
    assert all(case["passed"] for case in response_variants["cases"])
    previous = read_json(task / "validation/history/497a5b6/e2e-evidence.json")
    image = read_json(out / "image-audit.json")
    assert image["image_id"] == previous["image"]["image_id"]
    test_hashes = {
        k.removeprefix("tests/"): v for k, v in frozen.items() if k.startswith("tests/")
    }
    evidence = {
        "schema_version": previous["schema_version"],
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "validation_mode": "verifier_only",
        "source": previous["source"],
        "image": previous["image"],
        "runtime_assets": previous["runtime_assets"],
        "review_identity": read_json(out / "review-identity.json"),
        "artifacts": {
            "files": frozen,
            "tests_tree_sha256": hashlib.sha256(
                json.dumps(test_hashes, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        },
        "verifier_contract": {
            "pytest_cases": inventory["total_pytest_cases"],
            "sdk_fixture_cases": fixture_count,
            "rust_http_cases": server_count,
            "rust_anthropic_cases": server_count - native_count,
            "rust_existing_route_cases": native_count,
            "python_frontend_control_checks": 10,
            "public_boundary": previous["verifier_contract"]["public_boundary"],
            "substitution": "Deterministic Qwen token generation obeys the received max_tokens; real rendering, tokenization, engine-client IPC, output processing and SDK parsing execute. Full model computation and excluded SDK features remain unmeasured.",
            "solution_present": False,
        },
        "harbor": {
            "jobs": jobs,
            "trials": trials,
            "n_completed_trials": len(trials),
            "n_errored_trials": 0,
            "oracle_case_created_or_run": False,
            "control_agent_note": "Harbor oracle agents apply declared partial controls only; none is a complete Rust Anthropic solution.",
            "input_scope_note": "Trial checksums identify prepared inputs before evidence-only finalization. Frozen executable hashes match every prepared test and instruction.",
        },
        "stability": {
            "base_rounds": len(base),
            "identical_failed_names": True,
            "rewards": [t["reward"] for t in base],
        },
        "python_qualification": {
            "reference": python_reference["summary"],
            "results_sha256": sha(task / "validation/latest_python/results.json"),
            "correct_partial_alternative": alternative,
            "wrong_generation_limit": wrong_limit,
            "named_tool_alternative": named_alternative,
            "response_representation_alternatives": response_variants,
        },
        "current_image_audit": image,
        "independent_review": {
            "report": "validation/independent-review.md",
            "sha256": sha(task / "validation/independent-review.md"),
        },
        "known_limitation": previous["known_limitation"],
        "unmeasured_by_user_decision": previous["unmeasured_by_user_decision"],
        "instruction_scope_note": previous["instruction_scope_note"],
        "historical_evidence": "validation/history/497a5b6/e2e-evidence.json",
        "artifact_directory": str(out),
    }
    (task / "validation/e2e-evidence.json").write_text(
        json.dumps(evidence, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "harbor_trials": len(trials),
                "base_rounds": len(base),
                "python_cases": inventory["total_pytest_cases"],
                "executable_files": len(frozen),
                "errors": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
