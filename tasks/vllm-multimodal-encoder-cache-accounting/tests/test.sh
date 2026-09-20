#!/usr/bin/env bash
set -euo pipefail
# Keep rewards protected and readable by a non-root Harbor host.
test ! -L /logs/verifier
install -d -m 755 /logs/verifier
chown 0:0 /logs/verifier
rm -f /logs/verifier/reward.txt /logs/verifier/verification.json
printf '0\n' > /logs/verifier/reward.txt
chmod 644 /logs/verifier/reward.txt
report="$(mktemp /logs/verifier/.verification.XXXXXX)"
if cd /workspace/vllm && python3 -I -S /tests/trusted_python.py /tests/verify_encoder_cache.py > "$report" 2>&1; then
  printf '1\n' > /logs/verifier/reward.txt
fi
chmod 644 "$report"
mv -f "$report" /logs/verifier/verification.json
