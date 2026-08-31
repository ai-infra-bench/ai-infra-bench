#!/usr/bin/env bash
set -uo pipefail
mkdir -p /logs/verifier
cd /workspace/vllm
pytest_rc=0
integrity_rc=0
ray_channel_rc=0
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 timeout 600 \
  pytest --noconftest -c /dev/null --rootdir=/workspace/vllm \
    -p no:cacheprovider -v -s --junitxml=/logs/verifier/junit.xml \
    /tests/test_regression.py || pytest_rc=$?
python /tests/check_junit.py /logs/verifier/junit.xml || integrity_rc=$?
ray_cluster_rc=0
ray stop --force >/dev/null 2>&1 || true
ray start --head --node-ip-address=127.0.0.1 --port=6379 \
  --num-cpus=1 --num-gpus=0 --object-store-memory=200000000 \
  --plasma-directory=/tmp --include-dashboard=false --disable-usage-stats \
  > /logs/verifier/ray_head_start.log 2>&1 || ray_cluster_rc=$?
if [ "$ray_cluster_rc" -eq 0 ]; then
  ray start --address=127.0.0.1:6379 --node-ip-address=127.0.0.2 \
    --num-cpus=1 --num-gpus=0 --object-store-memory=200000000 \
    --plasma-directory=/tmp --disable-usage-stats \
    > /logs/verifier/ray_worker_start.log 2>&1 || ray_cluster_rc=$?
fi
if [ "$ray_cluster_rc" -eq 0 ]; then
  RAY_CGRAPH_get_timeout=2 timeout 90 python /tests/test_real_ray_channel.py \
    > /logs/verifier/real_ray_channel.log 2>&1 || ray_channel_rc=$?
else
  ray_channel_rc=$ray_cluster_rc
  cat /logs/verifier/ray_head_start.log /logs/verifier/ray_worker_start.log \
    > /logs/verifier/real_ray_channel.log 2>/dev/null || true
fi
ray stop --force >/dev/null 2>&1 || true
cat /logs/verifier/real_ray_channel.log
if [ "$pytest_rc" -eq 0 ] && [ "$integrity_rc" -eq 0 ] \
    && [ "$ray_cluster_rc" -eq 0 ] && [ "$ray_channel_rc" -eq 0 ]; then
  rc=0
  printf '1\n' > /logs/verifier/reward.txt
else
  rc=1
  printf '0\n' > /logs/verifier/reward.txt
fi
printf '{"reward":%s,"command_exit_code":%s,"pytest_exit_code":%s,"integrity_exit_code":%s,"ray_cluster_exit_code":%s,"ray_channel_exit_code":%s}\n' \
  "$([ "$rc" -eq 0 ] && printf 1 || printf 0)" "$rc" "$pytest_rc" \
  "$integrity_rc" "$ray_cluster_rc" "$ray_channel_rc" \
  > /logs/verifier/reward.json
exit 0
