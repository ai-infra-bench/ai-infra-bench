#!/usr/bin/env bash
set -euo pipefail
cd /workspace/repo
git apply /solution/oracle.patch
# The grading entry rebuilds the candidate source as the agent user before
# loading any native artifact. Apply the repair here; avoid a redundant build
# and temporary changes to the project's setup.py in the reference solution.
