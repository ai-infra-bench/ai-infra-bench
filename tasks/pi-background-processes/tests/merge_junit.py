#!/usr/bin/env python3
"""Merge per-case JUnit reports into one suite report.

The contract cases run one per process (each case is its own pi process lifetime, as in
real use: a quit shutdown ends the process, so no case may inherit process-wide state from
an earlier case). Each case report must contain exactly its own case and nothing else;
anything else is recorded as a failure of that case.

Usage: merge_junit.py <out.xml> <suite-name> <case-report>...   (report order = case order)
"""
import sys
import xml.etree.ElementTree as ET

from case_contract import CONTRACT_CASES


def main() -> int:
    out, suite_name, reports = sys.argv[1], sys.argv[2], sys.argv[3:]
    suite = ET.Element("testsuite", name=suite_name)
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for report in reports:
        expected = None
        with open(report + ".name", encoding="utf-8") as handle:
            expected = handle.read()
        try:
            root = ET.parse(report).getroot()
            ran = [c for c in root.findall(".//testcase") if not c.find("skipped") is not None]
        except (OSError, ET.ParseError):
            ran = []
        mine = [c for c in ran if c.attrib.get("name", "").split(" > ")[-1] == expected]
        if len(ran) == 1 and len(mine) == 1:
            case = mine[0]
        else:
            case = ET.Element("testcase", name=expected, classname="isolated")
            failure = ET.SubElement(case, "failure", message="isolated run did not report exactly this case")
            failure.text = f"report {report}: {len(ran)} executed cases, {len(mine)} named {expected!r}"
        suite.append(case)
        totals["tests"] += 1
        for tag, key in (("failure", "failures"), ("error", "errors"), ("skipped", "skipped")):
            if case.find(tag) is not None:
                totals[key] += 1
    for key, value in totals.items():
        suite.set(key, str(value))
    root = ET.Element("testsuites")
    root.append(suite)
    ET.ElementTree(root).write(out, encoding="utf-8", xml_declaration=True)
    return 0


if __name__ == "__main__":
    assert CONTRACT_CASES  # inventory present
    raise SystemExit(main())
