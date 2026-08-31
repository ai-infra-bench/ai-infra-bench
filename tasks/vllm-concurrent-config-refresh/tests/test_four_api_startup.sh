#!/usr/bin/env bash
set -euo pipefail

repro_dir=$(mktemp -d /tmp/config-refresh-e2e.XXXXXX)
server_pid=
cleanup() {
  if [ -n "$server_pid" ] && kill -0 "$server_pid" 2>/dev/null; then
    kill -TERM "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

model_dir="$repro_dir/model"
mkdir -p "$model_dir"
python - "$model_dir" <<'PY'
import sys
from transformers import OPTConfig, OPTForCausalLM
config = OPTConfig(
    vocab_size=64, hidden_size=128, ffn_dim=256, num_hidden_layers=1,
    num_attention_heads=4, max_position_embeddings=128,
    word_embed_proj_dim=128, do_layer_norm_before=True,
    pad_token_id=0, bos_token_id=1, eos_token_id=2,
)
OPTForCausalLM(config).save_pretrained(sys.argv[1], safe_serialization=True)
PY

gcc -shared -fPIC -O2 /tests/fail_config_once.c \
  -o "$repro_dir/libconfig_faults.so" -ldl
startup_log=/logs/verifier/four_api_startup.log
markers=/logs/verifier/config_fault_markers.log
: > "$startup_log"
: > "$markers"
LD_PRELOAD="$repro_dir/libconfig_faults.so" \
AIB_FAIL_CONFIG_PATH="$model_dir/config.json" \
AIB_FAULT_MARKER_PATH="$markers" \
VLLM_CPU_KVCACHE_SPACE=1 \
  vllm serve "$model_dir" \
    --api-server-count 4 --skip-tokenizer-init --dtype float32 \
    --max-model-len 64 --max-num-seqs 2 --max-num-batched-tokens 64 \
    --num-gpu-blocks-override 16 --block-size 32 --enforce-eager \
    --host 127.0.0.1 --port 18000 > "$startup_log" 2>&1 &
server_pid=$!

healthy=0
for _ in $(seq 1 600); do
  if ! kill -0 "$server_pid" 2>/dev/null; then break; fi
  if python - <<'PY' >/dev/null 2>&1
import httpx
raise SystemExit(
    0 if httpx.get("http://127.0.0.1:18000/health", timeout=0.5).status_code == 200
    else 1
)
PY
  then
    healthy=1
    break
  fi
  sleep 0.1
done

enoent=$(grep -c '^ApiServer_0 ENOENT$' "$markers" || true)
empty_read=$(grep -c '^ApiServer_1 EMPTY_READ$' "$markers" || true)
if [ "$healthy" -ne 1 ] || [ "$enoent" -ne 1 ] || [ "$empty_read" -ne 1 ]; then
  cat "$markers"
  tail -200 "$startup_log"
  exit 1
fi

MODEL_DIR="$model_dir" python - <<'PY'
import httpx, os
root = "http://127.0.0.1:18000"
assert httpx.get(f"{root}/health", timeout=5).status_code == 200
response = httpx.post(
    f"{root}/v1/completions",
    json={
        "model": os.environ["MODEL_DIR"],
        "prompt": [4] * 16,
        "max_tokens": 2,
        "ignore_eos": True,
        "temperature": 0,
    },
    timeout=30,
)
assert response.status_code == 200, response.text
payload = response.json()
assert len(payload["choices"]) == 1
assert payload["usage"]["completion_tokens"] > 0
print({"ready_workers": 4, "faults": 2, "http_status": response.status_code})
PY

kill -TERM "$server_pid" 2>/dev/null || true
wait "$server_pid" 2>/dev/null || true
server_pid=
