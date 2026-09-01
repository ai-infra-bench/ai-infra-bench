#!/usr/bin/env bash
set -euo pipefail
cd /workspace/vllm
mkdir -p rust/src/tool-parser/examples
cp /opt/repro/tool_parser_probe.rs \
  rust/src/tool-parser/examples/repro_tool_entities.rs
cargo build --quiet --manifest-path rust/Cargo.toml \
  -p vllm-tool-parser --example repro_tool_entities
wire='<minimax:tool_call><invoke name="write_file"><parameter name="content">Tom &amp; Jerry &lt;3</parameter></invoke></minimax:tool_call>'
output=$(rust/target/debug/examples/repro_tool_entities \
  minimax_m2 complete "$wire")
printf '%s\n' "$output"
python - "$output" <<'PY'
import json
import sys
value = json.loads(sys.argv[1])["calls"][0]["arguments"]["content"]
expected = "Tom &amp; Jerry &lt;3"
print(f"argument={value!r}")
print(f"literal_entities_preserved={value == expected}")
raise SystemExit(0 if value == expected else 3)
PY
