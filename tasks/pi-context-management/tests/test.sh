#!/bin/bash
set -u
umask 022
mkdir -p /logs/verifier
printf '0\n' > /logs/verifier/reward.txt
# Scorer stays in the parent; candidate Pi runs as the agent user.
chmod 755 /tests 2>/dev/null || true
chmod 600 /tests/verify.py 2>/dev/null || true
python3 /tests/verify.py --repo /workspace/pi --output /logs/verifier/behavior
status=$?
if [ "$status" -eq 0 ]; then
    printf '1\n' > /logs/verifier/reward.txt
fi
exit "$status"
