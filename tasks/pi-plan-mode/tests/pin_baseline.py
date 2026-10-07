#!/usr/bin/env python3
"""Authoring-only: pin a NEW Base run, never invoked by the scored verifier."""
import json
import sys
from pathlib import Path
from check_pass_to_pass import outcomes, digest
baseline = outcomes(Path(sys.argv[1]))
pins = {"base_commit": "d981de1229ef899957bbe968bc8dcda02a21f477", "cases": len(baseline), "outcomes_sha256": digest(baseline), "failed": sorted(k for k, v in baseline.items() if v == "failed"), "skipped": sum(v == "skipped" for v in baseline.values())}
Path(sys.argv[2]).write_text(json.dumps(pins, indent=2) + "\n"); print(json.dumps(pins))
