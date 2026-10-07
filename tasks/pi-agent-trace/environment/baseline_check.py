#!/usr/bin/env python3
"""Summarise the PASS_TO_PASS baseline recorded at image build time.

Writes /opt/pi-baseline/summary.json and fails the build when the suite did not
run at all or when the environmental failure set on Base is larger than the
small allowance (install-method detection when the install path is not
writable, and timing-sensitive cases that flake inside containers).
"""
import json
import sys
import xml.etree.ElementTree as ET

ALLOWED_ENVIRONMENTAL_FAILURES = 6

root = ET.parse("/opt/pi-baseline/coding-agent-junit.xml").getroot()
suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
totals = {k: sum(int(s.attrib.get(k, "0")) for s in suites) for k in ("tests", "failures", "errors", "skipped")}
failed = []
for case in root.findall(".//testcase"):
    if case.find("failure") is not None or case.find("error") is not None:
        failed.append(f"{case.attrib.get('classname', '')}::{case.attrib.get('name', '')}")
summary = {"totals": totals, "failed_on_base": failed}
with open("/opt/pi-baseline/summary.json", "w") as stream:
    stream.write(json.dumps(summary, indent=2) + "\n")
print("baseline", totals)
for name in failed:
    print("  failed on base:", name)
if totals["tests"] < 2000:
    print("baseline suite did not run", file=sys.stderr)
    sys.exit(1)
if totals["failures"] + totals["errors"] > ALLOWED_ENVIRONMENTAL_FAILURES:
    print("too many environmental failures on Base; fix the image", file=sys.stderr)
    sys.exit(1)
