#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier

# Trusted parent runs as root, spawns worker as nobody, writes reward.txt itself
if cd /app && python3 -I -S /tests/trusted_python.py /tests/verify_encoder_cache.py > /logs/verifier/verification.json 2>&1; then
  printf '1\n' > /logs/verifier/reward.txt
else
  printf '0\n' > /logs/verifier/reward.txt
fi
