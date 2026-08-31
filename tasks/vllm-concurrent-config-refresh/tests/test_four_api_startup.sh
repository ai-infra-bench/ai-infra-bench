#!/usr/bin/env bash
set -euo pipefail

repro_dir=$(mktemp -d /tmp/harbor-config-refresh.XXXXXX)
server_pid=
cleanup() {
  if [ -n "$server_pid" ] && kill -0 "$server_pid" 2>/dev/null; then
    kill -TERM "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
  rm -rf "$repro_dir"
}
trap cleanup EXIT

model_dir="$repro_dir/model"
mkdir -p "$model_dir"
python -c '
from transformers import OPTConfig, OPTForCausalLM
config = OPTConfig(
    vocab_size=256,
    hidden_size=64,
    ffn_dim=256,
    num_hidden_layers=2,
    num_attention_heads=4,
    max_position_embeddings=128,
    word_embed_proj_dim=64,
    do_layer_norm_before=True,
)
OPTForCausalLM(config).save_pretrained("'"$model_dir"'", safe_serialization=True)
'

gcc -shared -fPIC -O2 /tests/fail_config_once.c \
  -o "$repro_dir/libfail_config_once.so" -ldl

startup_log=/logs/verifier/four_api_startup.log
: > "$startup_log"
LD_PRELOAD="$repro_dir/libfail_config_once.so" \
AIB_FAIL_CONFIG_PATH="$model_dir/config.json" \
  vllm serve "$model_dir" \
    --api-server-count 4 \
    --skip-tokenizer-init \
    --dtype float32 \
    --max-model-len 64 \
    --max-num-seqs 1 \
    --max-num-batched-tokens 64 \
    --gpu-memory-utilization 0.5 \
    --enforce-eager \
    --host 127.0.0.1 \
    --port 18000 > "$startup_log" 2>&1 &
server_pid=$!

ready=0
for _ in $(seq 1 600); do
  ready=$(grep -Ec '\(ApiServer_[0-3] pid=.*Application startup complete' \
    "$startup_log" || true)
  if [ "$ready" -eq 4 ]; then
    break
  fi
  if ! kill -0 "$server_pid" 2>/dev/null; then
    break
  fi
  sleep 0.1
done

failed_workers=$(grep -Ec 'Process ApiServer_[0-3]:' "$startup_log" || true)
resolved=$(grep -Ec '\(ApiServer_[0-3] pid=.*Resolved architecture' \
  "$startup_log" || true)
retries=$(grep -c 'Error parsing config.*retrying 1 of 2' \
  "$startup_log" || true)

if [ "$ready" -ne 4 ] || [ "$failed_workers" -ne 0 ] \
  || [ "$resolved" -ne 4 ] || [ "$retries" -ne 1 ]; then
  tail -200 "$startup_log"
  exit 1
fi

kill -TERM "$server_pid" 2>/dev/null || true
wait "$server_pid" 2>/dev/null || true
server_pid=
