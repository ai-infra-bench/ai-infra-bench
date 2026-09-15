#!/usr/bin/env python3
"""Collect completed Harbor results and hash the exact reviewable task snapshot."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matrix", type=Path)
    args = parser.parse_args()
    task = Path(__file__).resolve().parent.parent
    matrix = json.loads((args.matrix / "summary.json").read_text())
    image = json.loads((task / "environment/image-manifest.json").read_text())
    expected = {"base": 0, "oracle": 1}
    expected.update({item["name"]: item["expected_reward"] for item in json.loads((task / "validation/ci-cases.json").read_text())["cases"]})
    names = [item["case"] for item in matrix["results"]]
    if len(names) != len(set(names)) or set(names) != set(expected):
        raise ValueError("Matrix must include Base, Oracle, alternative and every declared control exactly once")
    if matrix["image"] != image["image_id"]:
        raise ValueError("Matrix image does not match retained task image")
    runs = []
    for item in matrix["results"]:
        if item["expected_reward"] != expected[item["case"]]:
            raise ValueError("Matrix expected reward differs from frozen cases")
        if item["harbor_exit_code"] or item["check_exit_code"]:
            raise ValueError(f"Unaccepted author run: {item['case']}")
        prepared = Path(item["command"][item["command"].index("--path") + 1])
        common = [Path("instruction.md"), *[p.relative_to(task) for p in (task / "tests").rglob("*") if p.is_file() and "__pycache__" not in p.parts]]
        if any(digest(task / rel) != digest(prepared / rel) for rel in common):
            raise ValueError(f"Trial snapshot differs from final instruction/verifier: {item['case']}")
        result_path = Path(item["result"])
        check = json.loads(item["check_output"])
        if check != {"completed": 1, "errored": 0, "rewards": [float(item["expected_reward"]) ]}:
            raise ValueError(f"Unexpected Harbor result: {check}")
        summaries = {}
        for filename in ("contract-summary.json", "lifecycle-summary.json", "pass-to-pass-summary.json", "scope.json", "reward.json"):
            matches = list(result_path.parent.rglob(filename))
            if len(matches) != 1:
                raise ValueError(f"Expected one {filename} in {result_path.parent}, found {len(matches)}")
            summaries[filename] = json.loads(matches[0].read_text())
        if not summaries["scope.json"]["passed"] or not summaries["pass-to-pass-summary.json"]["passed"]:
            raise ValueError(f"A scope or unrelated regression failure occurred: {item['case']}")
        behavior_passed = summaries["contract-summary.json"]["passed"] and summaries["lifecycle-summary.json"]["passed"]
        if behavior_passed != bool(item["expected_reward"]):
            raise ValueError(f"Behavioral result does not explain reward: {item['case']}")
        raw_hashes = {str(p.relative_to(result_path.parent)): digest(p) for p in result_path.parent.rglob("*") if p.is_file() and (p.suffix in {".xml", ".json"} or p.name in {"pass-to-pass.log", "contract.log", "lifecycle.log"})}
        runs.append({**item, "observed": check, "result_sha256": digest(result_path), "verifier": summaries, "raw_artifact_sha256": raw_hashes})

    files = {}
    for path in sorted(task.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.name not in {"e2e-evidence.json", ".DS_Store"}:
            files[path.relative_to(task).as_posix()] = digest(path)
    evidence = {
        "schema_version": "ai_infra_bench_e2e_evidence.v1",
        "task": "ai-infra-bench/pi-plan-mode",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "base_commit": image["base_commit"],
        "dependency_cutoff": image["dependency_cutoff"],
        "image": {key: image[key] for key in ("canonical_tag", "image_id", "platform", "build_context")},
        "harbor_version": matrix["harbor"],
        "hardware": "Developer machine, native Linux amd64, each final Harbor trial uses 4 CPUs and 8192 MiB; network disabled",
        "semantic_boundary": "user input / scripted model tool call -> real loader, AgentSession, dispatch, approval and persistence -> visible requests, tool effects, control entries and independent-process resume",
        "substitutions": ["first-party faux provider for model output", "UI choice adapter for a human selecting an action"],
        "artifacts": {"files": files},
        "harbor_runs": runs,
        "other_checks": {
            "oracle": "Final retained image, actual pi-agent user: npm run check and 43 extension/utils tests pass; remote oracle-code-check-final.log",
            "alternative": "Independently written event journal/reducer; npm run check, 42 own/utils tests and 21 business/lifecycle checks pass before formal same-verifier run",
            "agent_environment": "Final retained image, pi-agent UID 1001 offline: 60 path/settings smoke tests pass; prior permissions-equivalent image also passed full npm run check",
            "initial_image_baseline": image["pass_to_pass_baseline"],
        },
        "limitations": [
            "Author validation only; no real coding-agent rollout or empirical difficulty/success-rate claim.",
            "One original AuthStorage failure was reproduced on untouched Base and is accepted only under its exact pinned assertion fingerprint; all 2154 cases remain required, with raw failures exposed.",
            "Existing public Plan Mode implementations may inform solvers; no contamination-free claim.",
            "Root reporter and protected toolchain prevent worker writes to grading artifacts; not a universal defense against arbitrary assertion manipulation within a worker.",
            "The retained local image is immutable by ID; floating OS repositories/frontend mean later Dockerfile builds need not be byte-identical. Image not published.",
            "Crash recovery, in-flight shutdown, fork/tree/reload and arbitrary shell read-only enforcement are outside this task.",
        ],
        "delivery": {"branch": "agent/pi-plan-mode", "committed": False, "pushed": False,
                     "developer_worktree": "/data00/home/xingjunqian/ai-infra-bench-plan-mode"},
    }
    target = task / "validation/e2e-evidence.json"
    target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(target)


if __name__ == "__main__":
    main()
