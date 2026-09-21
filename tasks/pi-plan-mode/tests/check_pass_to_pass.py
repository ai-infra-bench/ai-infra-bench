#!/usr/bin/env python3
"""Require every freshly pinned Base testcase and outcome; reject missing/duplicate reports."""
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

def outcomes(path):
    root = ET.parse(path).getroot(); result = {}
    for case in root.findall(".//testcase"):
        key = f"{case.get('classname', '')}::{case.get('name', '')}"
        if key in result: raise ValueError(f"duplicate case {key}")
        result[key] = "skipped" if case.find("skipped") is not None else "failed" if any(case.find(k) is not None for k in ("failure", "error")) else "passed"
    if not result: raise ValueError("empty JUnit report")
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    if sum(int(s.get("tests", 0)) for s in suites) != len(result): raise ValueError("testcase count disagrees with suite totals")
    for tag, value in [("skipped", "skipped"), ("failures", "failed")]:
        # An error element contributes to failed outcomes too; combine attributes.
        total = sum(int(s.get(tag, 0)) + (int(s.get("errors", 0)) if tag == "failures" else 0) for s in suites)
        if total != sum(v == value for v in result.values()): raise ValueError(f"{tag} aggregate disagrees")
    # The image records the complete fresh Base suite. The public task explicitly
    # replaces this one original test file's behavior, so project it out of BOTH
    # maps after validating the full raw XML inventory/aggregate consistency.
    return {key: value for key, value in result.items() if PurePosixPath(key.split("::", 1)[0].replace("\\", "/")).name != "plan-mode-extension.test.ts"}

def digest(value): return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

KNOWN_BASE_CASE = "test/auth-storage.test.ts::AuthStorage > keeps a coalesced reload alive while another credential reader is waiting"
KNOWN_BASE_SIGNATURE = {
    "case": KNOWN_BASE_CASE,
    "failure_type": "AssertionError",
    "failure_message": "expected { type: 'api_key', key: 'old' } to deeply equal { type: 'api_key', key: 'new' }",
    "stack_contains": "test/auth-storage.test.ts:137:22",
}

def observed_known_base_failures(path, pins):
    specifications = pins.get("allowed_environmental_failures", [])
    if not specifications: return set()
    if len(specifications) != 1 or any(specifications[0].get(k) != v for k, v in KNOWN_BASE_SIGNATURE.items()):
        raise ValueError("unsupported known Base failure specification")
    evidence = specifications[0].get("evidence", [])
    if not evidence or any(not item.get("path") or len(item.get("sha256", "")) != 64 for item in evidence):
        raise ValueError("known Base failure lacks pinned evidence")
    found = set()
    for case in ET.parse(path).getroot().findall(".//testcase"):
        key = f"{case.get('classname', '')}::{case.get('name', '')}"
        if key != KNOWN_BASE_CASE: continue
        failures = case.findall(".//failure")
        if not 1 <= len(failures) <= 3 or case.find(".//error") is not None or case.find(".//skipped") is not None: continue
        # Vitest records each failed attempt when --retry=2 is active. Every
        # attempt must exhibit this exact observed Base assertion.
        if all(failure.get("type") == KNOWN_BASE_SIGNATURE["failure_type"] and
               failure.get("message") == KNOWN_BASE_SIGNATURE["failure_message"] and
               KNOWN_BASE_SIGNATURE["stack_contains"] in (failure.text or "") for failure in failures):
            found.add(key)
    return found

def compare(base, current, observed=()):
    observed = set(observed)
    if observed - {KNOWN_BASE_CASE}: raise ValueError("unexpected known Base failure")
    if any(base.get(k) != "passed" or current.get(k) != "failed" for k in observed): raise ValueError("known Base failure has wrong outcome")
    missing = sorted(set(base) - set(current)); extra = sorted(set(current) - set(base))
    regressions = sorted(k for k, v in base.items() if
        (v == "passed" and current.get(k) != "passed" and k not in observed) or
        (v == "skipped" and current.get(k) != "skipped") or
        (v == "failed" and current.get(k) not in {"failed", "passed"}))
    return dict(passed=not (missing or extra or regressions), baseline_cases=len(base), candidate_cases=len(current),
        missing=missing, extra=extra, regressions=regressions, observed_known_base_failures=sorted(observed))

def main():
    baseline, candidate, pins_path = map(Path, sys.argv[1:4]); report = {"passed": False}
    try:
        pins = json.loads(pins_path.read_text()); base = outcomes(baseline); current = outcomes(candidate)
        if pins.get("base_commit") != "d981de1229ef899957bbe968bc8dcda02a21f477": raise ValueError("unexpected Base commit")
        if digest(base) != pins["outcomes_sha256"] or len(base) != pins["cases"]: raise ValueError("baseline outcome inventory changed")
        report.update(compare(base, current, observed_known_base_failures(candidate, pins)))
    except (OSError, ValueError, KeyError, ET.ParseError) as error: report["error"] = str(error)
    candidate.parent.mkdir(parents=True, exist_ok=True); (candidate.parent / "pass-to-pass-summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report)); return 0 if report["passed"] else 1

if __name__ == "__main__": raise SystemExit(main())
