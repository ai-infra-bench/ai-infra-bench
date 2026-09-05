"""Ensure the existing server/chat suites really ran; allow added tests."""
import json
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text()
summaries = re.findall(r"test result: (\w+)\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out", text)
passed = sum(int(row[1]) for row in summaries)
valid = len(summaries) == 2 and passed >= 673 and all(
    row[0] == "ok" and all(int(value) == 0 for value in row[2:]) for row in summaries
)
print(json.dumps({"suites": len(summaries), "passed": passed, "minimum_baseline_tests": 673, "valid": valid}))
raise SystemExit(0 if valid else 1)
