#!/usr/bin/env bash
set -uo pipefail

asset_dir=/opt/harbor-assets/qwen3.5-27b
work_dir=$(mktemp -d /tmp/harbor-anthropic-sdk.XXXXXX)
model_dir="$work_dir/model"
server_log=/logs/verifier/anthropic_api_server.log
probe_log=/logs/verifier/anthropic_sdk_probe.log
port=18080
server_pid=

cleanup() {
  if [ -n "$server_pid" ] && kill -0 "$server_pid" 2>/dev/null; then
    kill -TERM -- "-$server_pid" 2>/dev/null || true
    for _ in $(seq 1 30); do
      kill -0 "$server_pid" 2>/dev/null || break
      sleep 0.2
    done
    kill -KILL -- "-$server_pid" 2>/dev/null || true
  fi
  rm -rf "$work_dir"
}
trap cleanup EXIT

for required in config.json tokenizer.json tokenizer_config.json chat_template.jinja; do
  if [ ! -f "$asset_dir/$required" ]; then
    echo "missing pinned Qwen runtime asset: $required" >&2
    exit 1
  fi
done
if find "$asset_dir" -type f \
    \( -name '*.bin' -o -name '*.gguf' -o -name '*.pt' -o -name '*.pth' -o -name '*.safetensors' \) \
    -print -quit | grep -q .; then
  echo "model tensor found in metadata-only Qwen runtime assets" >&2
  exit 1
fi

mkdir -p "$model_dir"
cat > "$model_dir/config.json" <<'MODEL_CONFIG_EOF'
{
  "_remove_final_layer_norm": false,
  "activation_function": "relu",
  "architectures": ["OPTForCausalLM"],
  "attention_dropout": 0.0,
  "bos_token_id": 2,
  "do_layer_norm_before": true,
  "dropout": 0.0,
  "dtype": "float32",
  "enable_bias": true,
  "eos_token_id": 2,
  "ffn_dim": 512,
  "hidden_size": 256,
  "init_std": 0.02,
  "layer_norm_elementwise_affine": true,
  "layerdrop": 0.0,
  "max_position_embeddings": 512,
  "model_type": "opt",
  "num_attention_heads": 4,
  "num_hidden_layers": 2,
  "pad_token_id": 1,
  "tie_word_embeddings": true,
  "use_cache": true,
  "vocab_size": 248320,
  "word_embed_proj_dim": 256
}
MODEL_CONFIG_EOF

: > "$server_log"
: > "$probe_log"
setsid env \
  GLOO_SOCKET_IFNAME=lo \
  VLLM_CPU_KVCACHE_SPACE=1 \
  VLLM_HOST_IP=127.0.0.1 \
  vllm serve "$model_dir" \
    --host 127.0.0.1 \
    --port "$port" \
    --served-model-name Qwen3.6-27B \
    --tokenizer "$asset_dir" \
    --chat-template "$asset_dir/chat_template.jinja" \
    --load-format dummy \
    --dtype float32 \
    --max-model-len 512 \
    --max-num-batched-tokens 512 \
    --max-num-seqs 1 \
    --enforce-eager \
    >"$server_log" 2>&1 &
server_pid=$!

ready=0
for _ in $(seq 1 120); do
  if curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
  if ! kill -0 "$server_pid" 2>/dev/null; then
    break
  fi
  sleep 1
done
if [ "$ready" -ne 1 ]; then
  echo "vLLM Anthropic API server did not become ready" >&2
  tail -n 120 "$server_log" >&2
  exit 1
fi

ANTHROPIC_BASE_URL="http://127.0.0.1:$port" \
  python /tests/anthropic_sdk_probe.py 2>&1 | tee "$probe_log"
probe_rc=${PIPESTATUS[0]}
exit "$probe_rc"
