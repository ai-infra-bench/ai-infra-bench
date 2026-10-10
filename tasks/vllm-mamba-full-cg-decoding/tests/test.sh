#!/usr/bin/env bash
set -euo pipefail
mkdir -p /logs/verifier
chmod 0755 /logs/verifier
printf '0\n' > /logs/verifier/reward.txt
printf '{"reward":0}\n' > /logs/verifier/reward.json
chmod 0600 /logs/verifier/reward.txt /logs/verifier/reward.json
stage=/opt/ai-infra-verifier
mkdir -p "$stage"
chmod 0755 "$stage"
install -m 0644 -o 0 -g 0 /tests/supervise_verifier.py "$stage/supervise_verifier.py"
install -m 0644 -o 0 -g 0 /tests/verify_mamba_full_cg.py "$stage/verify_mamba_full_cg.py"
install -m 0644 -o 0 -g 0 /tests/observe_cuda_graph.c "$stage/observe_cuda_graph.c"
/usr/bin/gcc -std=c11 -O2 -Wall -Wextra -Werror "$stage/observe_cuda_graph.c" -o "$stage/observe_cuda_graph"
chmod 0755 "$stage/observe_cuda_graph"
# Ignore all candidate Python search paths and startup hooks in the scorer.
unset PYTHONPATH PYTHONHOME LD_PRELOAD
cd /
exec /usr/bin/python3 -I "$stage/supervise_verifier.py"
