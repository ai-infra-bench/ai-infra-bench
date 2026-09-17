#!/usr/bin/env python3
"""PASS_TO_PASS: every pi test case that passed on Base must still pass, the set of
skipped Base cases must be unchanged, and no case may fail unless it already
failed on Base (the image records that baseline).

Usage: check_pass_to_pass.py <baseline-junit.xml> <candidate-junit.xml> [baseline-pins.json]
"""

from __future__ import annotations

import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def outcomes(path: Path) -> dict[str, str]:
    root = ET.parse(path).getroot()
    result: dict[str, str] = {}
    for case in root.findall(".//testcase"):
        key = f"{case.attrib.get('classname', '')}::{case.attrib.get('name', '')}"
        if case.find("skipped") is not None:
            result[key] = "skipped"
        elif case.find("failure") is not None or case.find("error") is not None:
            result[key] = "failed"
        else:
            result[key] = "passed"
    return result


def digest(keys) -> str:
    return hashlib.sha256("\n".join(sorted(keys)).encode()).hexdigest()


def check_pins(baseline: dict[str, str], pins: dict[str, object]) -> list[str]:
    """The baseline lives in the agent-writable image, so its identity is pinned
    here by content that is deterministic across builds and platforms: the exact
    set of case names at Base, the exact set of key-gated skipped cases, and a
    cap on environmental failures. A rewritten baseline (e.g. everything marked
    failed) cannot satisfy these."""
    problems = []
    if digest(baseline) != pins["case_names_sha256"]:
        problems.append("baseline case-name set does not match the pinned Base inventory")
    skipped = [k for k, v in baseline.items() if v == "skipped"]
    if digest(skipped) != pins["skipped_sha256"]:
        problems.append("baseline skipped set does not match the pinned key-gated set")
    failed = [k for k, v in baseline.items() if v == "failed"]
    if len(failed) > int(pins["max_failures"]):
        problems.append(
            f"baseline records {len(failed)} failures, more than the pinned maximum {pins['max_failures']}"
        )
    # Only the known environmental failures may be marked failed on Base; a
    # baseline that exempts any other case is a rewrite, not a build artifact.
    allowed = set(pins.get("allowed_failures", []))
    unexpected = sorted(k for k in failed if k not in allowed)
    if unexpected:
        problems.append(
            f"baseline marks cases as failed on Base that are not in the pinned allowed set: {unexpected[:5]}"
        )
    return problems


def main() -> int:
    baseline_path, candidate_path = Path(sys.argv[1]), Path(sys.argv[2])
    pins_path = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    summary: dict[str, object] = {"passed": False}
    try:
        baseline = outcomes(baseline_path)
        candidate = outcomes(candidate_path)
        pins = json.loads(pins_path.read_text()) if pins_path else {}
        pin_problems = check_pins(baseline, pins) if pins_path else []
        summary["baseline_pin_problems"] = pin_problems
        # The pinned environmental failures are timing- or platform-dependent cases of pi's
        # own suite (recorded from several image builds); when one of them fails in the
        # candidate run it is tolerated, whatever the baseline of this particular build did.
        tolerated_set = set(pins.get("allowed_failures", []))
        missing = sorted(k for k in baseline if k not in candidate)
        regressed = sorted(
            k
            for k, v in baseline.items()
            if v == "passed" and candidate.get(k) != "passed" and k not in tolerated_set
        )
        skip_changed = sorted(
            k for k, v in baseline.items() if v == "skipped" and candidate.get(k) != "skipped"
        )
        newly_skipped = sorted(
            k for k, v in candidate.items() if v == "skipped" and baseline.get(k) != "skipped"
        )
        # Cases that already failed on Base (environment-specific, recorded in the
        # image baseline) are not the candidate's regression; every other failure is.
        failed = sorted(
            k
            for k, v in candidate.items()
            if v == "failed" and baseline.get(k) != "failed" and k not in tolerated_set
        )
        tolerated = sorted(
            k for k, v in candidate.items() if v == "failed" and k in tolerated_set
        )
        summary.update(
            baseline_cases=len(baseline),
            candidate_cases=len(candidate),
            missing=missing,
            regressed=regressed,
            tolerated=tolerated,
            skip_changed=skip_changed,
            newly_skipped=newly_skipped,
            failed=failed,
            passed=not (
                missing or regressed or skip_changed or newly_skipped or failed or pin_problems
            )
            and len(baseline) > 0,
        )
    except (OSError, ValueError, ET.ParseError) as error:
        summary["error"] = f"{type(error).__name__}: {error}"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    (candidate_path.parent / "pass-to-pass-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps({k: (v if not isinstance(v, list) else v[:20]) for k, v in summary.items()}))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
