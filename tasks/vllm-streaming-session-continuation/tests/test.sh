#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
printf "0\n" > /logs/verifier/reward.txt
python3 -I -S /tests/trusted_score.py
exit 0
