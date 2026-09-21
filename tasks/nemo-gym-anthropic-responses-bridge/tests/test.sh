#!/bin/bash
set -euo pipefail
mkdir -p /logs/verifier
chmod 700 /logs/verifier /tests
printf '0\n' > /logs/verifier/reward.txt
# Candidate source is never imported by this trusted parent interpreter.
python -I /tests/prepare.py
exec python -I /tests/grade.py --repo /workspace/Gym --python /usr/local/bin/python \
  --fixture /opt/bridge-fixture.py --candidate-user agent --output /logs/verifier
