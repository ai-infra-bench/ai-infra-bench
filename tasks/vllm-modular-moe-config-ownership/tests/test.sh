#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
printf "0\n" > /logs/verifier/reward.txt
cd /
python3 -I -S /tests/trusted_score.py /tests/verify_parallel_config.py
exit 0
