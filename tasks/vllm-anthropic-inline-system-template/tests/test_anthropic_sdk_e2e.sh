#!/usr/bin/env bash
set -euo pipefail

asset_dir=/opt/models/qwen-template
work_dir=$(mktemp -d /tmp/anthropic-inline-system.XXXXXX)
model_dir="$work_dir/model"
mkdir -p "$model_dir"

for required in config.json tokenizer.json tokenizer_config.json chat_template.jinja; do
  test -f "$asset_dir/$required"
done
if find "$asset_dir" -type f \
    \( -name '*.bin' -o -name '*.gguf' -o -name '*.pt' -o -name '*.pth' -o -name '*.safetensors' \) \
    -print -quit | grep -q .; then
  echo "model tensor found in metadata-only Qwen runtime assets" >&2
  exit 1
fi

cat > "$model_dir/config.json" <<'EOF'
{
  "architectures": ["OPTForCausalLM"],
  "activation_function": "relu",
  "bos_token_id": 2,
  "do_layer_norm_before": true,
  "dtype": "float32",
  "eos_token_id": 2,
  "ffn_dim": 512,
  "hidden_size": 256,
  "max_position_embeddings": 1024,
  "model_type": "opt",
  "num_attention_heads": 4,
  "num_hidden_layers": 2,
  "pad_token_id": 1,
  "vocab_size": 248320,
  "word_embed_proj_dim": 256
}
EOF

cat > "$work_dir/restrictive_sentinel.jinja" <<'EOF'
{%- set ns = namespace(system_count=0) -%}
{%- for message in messages -%}
  {%- if message.role == 'system' -%}
    {%- set ns.system_count = ns.system_count + 1 -%}
    {%- if not loop.first -%}{{ raise_exception('System message must be first') }}{%- endif -%}
  {%- endif -%}
{%- endfor -%}
{%- if messages and messages[0].content != 't' -%}
  {%- set merged_system = messages[0].content -%}
  {%- if ns.system_count != 1 -%}{{ raise_exception('Expected one merged system message') }}{%- endif -%}
  {%- if merged_system.count('LEAD_SENTINEL') != 1 -%}{{ raise_exception('Leading system content must appear exactly once') }}{%- endif -%}
  {%- if merged_system.count('INLINE_SENTINEL') != 1 -%}{{ raise_exception('Inline system content must appear exactly once') }}{%- endif -%}
  {%- if merged_system.find('LEAD_SENTINEL') > merged_system.find('INLINE_SENTINEL') -%}{{ raise_exception('System content order changed') }}{%- endif -%}
  {%- if messages|length != 4 -%}{{ raise_exception('Conversation message count changed') }}{%- endif -%}
  {%- if messages[1].role != 'user' or messages[1].content != 'diagnostic user turn' -%}{{ raise_exception('First user turn changed') }}{%- endif -%}
  {%- if messages[2].role != 'assistant' or messages[2].content != 'diagnostic assistant turn' -%}{{ raise_exception('Assistant turn changed') }}{%- endif -%}
  {%- if messages[3].role != 'user' or messages[3].content != 'continue' -%}{{ raise_exception('Final user turn changed') }}{%- endif -%}
{%- endif -%}
{%- for message in messages -%}{{ message.role }}:{{ message.content }}
{%- endfor -%}
{%- if add_generation_prompt -%}assistant:{%- endif -%}
EOF

cat > "$work_dir/permissive_position.jinja" <<'EOF'
{%- if messages and messages[0].content != 't' -%}
  {%- if messages|length != 4 -%}{{ raise_exception('Message count changed') }}{%- endif -%}
  {%- if messages[0].role != 'user' or messages[0].content != 'PERMISSIVE_USER_1' -%}{{ raise_exception('First user turn moved') }}{%- endif -%}
  {%- if messages[1].role != 'assistant' or messages[1].content != 'PERMISSIVE_ASSISTANT' -%}{{ raise_exception('Assistant turn moved') }}{%- endif -%}
  {%- if messages[2].role != 'system' or messages[2].content != 'PERMISSIVE_INLINE_SENTINEL' -%}{{ raise_exception('Inline system position changed') }}{%- endif -%}
  {%- if messages[3].role != 'user' or messages[3].content != 'PERMISSIVE_USER_2' -%}{{ raise_exception('Final user turn moved') }}{%- endif -%}
{%- endif -%}
{%- for message in messages -%}{{ message.role }}:{{ message.content }}
{%- endfor -%}
{%- if add_generation_prompt -%}assistant:{%- endif -%}
EOF

server_pid=
stop_server() {
  if [ -n "$server_pid" ] && kill -0 "$server_pid" 2>/dev/null; then
    kill -TERM -- "-$server_pid" 2>/dev/null || true
    for _ in $(seq 1 50); do
      kill -0 "$server_pid" 2>/dev/null || break
      sleep 0.2
    done
    kill -KILL -- "-$server_pid" 2>/dev/null || true
  fi
  server_pid=
}
trap stop_server EXIT

run_mode() {
  mode=$1
  template=$2
  port=$3
  served_model=$4
  server_log="/logs/verifier/${mode}_server.log"
  result_json="/logs/verifier/${mode}_probe.json"
  setsid env GLOO_SOCKET_IFNAME=lo VLLM_CPU_KVCACHE_SPACE=1 \
    VLLM_HOST_IP=127.0.0.1 \
    vllm serve "$model_dir" --host 127.0.0.1 --port "$port" \
      --served-model-name "$served_model" --tokenizer "$asset_dir" \
      --chat-template "$template" --load-format dummy --dtype float32 \
      --max-model-len 1024 --max-num-batched-tokens 1024 --max-num-seqs 8 \
      --enforce-eager >"$server_log" 2>&1 &
  server_pid=$!
  ready=0
  for _ in $(seq 1 120); do
    if curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1; then
      ready=1
      break
    fi
    if ! kill -0 "$server_pid" 2>/dev/null; then break; fi
    sleep 1
  done
  if [ "$ready" -ne 1 ]; then
    tail -120 "$server_log" >&2
    return 1
  fi
  ANTHROPIC_BASE_URL="http://127.0.0.1:$port" PROBE_MODE="$mode" \
    SERVED_MODEL="$served_model" python /tests/anthropic_sdk_probe.py >"$result_json"
  stop_server
}

run_mode official_qwen "$asset_dir/chat_template.jinja" 18080 Qwen3.6-27B
run_mode restrictive_sentinel "$work_dir/restrictive_sentinel.jinja" 18081 hidden-restrictive-model
run_mode permissive "$work_dir/permissive_position.jinja" 18082 hidden-permissive-model
