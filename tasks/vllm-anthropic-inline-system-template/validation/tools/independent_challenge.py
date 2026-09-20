#!/usr/bin/env python3
"""Challenge a final candidate through HTTP with a separately derived case.

Run inside the pinned task image after applying the candidate, with tests at
/tests and an output mount at /logs/verifier. This is curator-only validation.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile

import anthropic

from anthropic_sdk_probe import count_tokens, create_message, stream_message
from run_api_checks import ASSET_DIR, MODEL_CONFIG, stop_server, wait_ready

TEMPLATE = """
{%- for message in messages -%}
  {%- if message.role == 'system' and not loop.first -%}
    {{ raise_exception('系统指令只能放在对话开头。') }}
  {%- endif -%}
{%- endfor -%}
{%- set text = messages[0].content -%}
{%- if messages|length != 4 or messages[0].role != 'system' -%}
  {{ raise_exception('Invalid conversation structure') }}
{%- endif -%}
{%- for marker in ['方向α', '保留β', '结束γ'] -%}
  {%- if text.count(marker) != 1 -%}{{ raise_exception('Instruction loss or duplication') }}{%- endif -%}
{%- endfor -%}
{%- if not (text.find('方向α') < text.find('保留β') < text.find('结束γ')) -%}
  {{ raise_exception('Instruction order changed') }}
{%- endif -%}
{%- if messages[1].role != 'user' or messages[1].content != 'Question ✓' -%}{{ raise_exception('User changed') }}{%- endif -%}
{%- if messages[2].role != 'assistant' or messages[2].content != 'Acknowledged.' -%}{{ raise_exception('Assistant changed') }}{%- endif -%}
{%- if messages[3].role != 'user' or messages[3].content != 'Continue.' -%}{{ raise_exception('Last turn changed') }}{%- endif -%}
{{- strftime_now('UTC') -}}
{%- for message in messages -%}{{ message.role }}:{{ message.content }}
{%- endfor -%}
{%- if add_generation_prompt -%}assistant:{%- endif -%}
"""


def main():
    output = Path("/logs/verifier")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="independent-inline-") as temporary:
        work = Path(temporary)
        (work / "model").mkdir()
        (work / "model/config.json").write_text(json.dumps(MODEL_CONFIG))
        template = work / "template.jinja"
        template.write_text(TEMPLATE)
        command = [
            "vllm", "serve", str(work / "model"), "--host", "127.0.0.1", "--port", "18109",
            "--served-model-name", "challenge-model", "--tokenizer", str(ASSET_DIR),
            "--chat-template", str(template), "--load-format", "dummy", "--dtype", "float32",
            "--max-model-len", "1024", "--max-num-batched-tokens", "1024", "--max-num-seqs", "8",
            "--enforce-eager",
        ]
        env = dict(os.environ, GLOO_SOCKET_IFNAME="lo", VLLM_CPU_KVCACHE_SPACE="1", VLLM_HOST_IP="127.0.0.1")
        with (output / "server.log").open("w") as log:
            server = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                wait_ready(server, "http://127.0.0.1:18109")
                kwargs = {
                    "model": "challenge-model", "system": "方向α",
                    "messages": [
                        {"role": "user", "content": "Question ✓"},
                        {"role": "assistant", "content": "Acknowledged."},
                        {"role": "system", "content": [{"type": "text", "text": "保留β"}]},
                        {"role": "system", "content": "结束γ"},
                        {"role": "user", "content": "Continue."},
                    ],
                }
                with anthropic.Anthropic(api_key="test", base_url="http://127.0.0.1:18109", timeout=30, max_retries=0) as client:
                    results = {"count_tokens": count_tokens(client, kwargs),
                               "messages": create_message(client, kwargs),
                               "stream": stream_message(client, kwargs)}
                passed = all(value["ok"] for value in results.values())
                if passed:
                    passed = len({value["input_tokens"] for value in results.values()}) == 1
                (output / "result.json").write_text(json.dumps({
                    "passed": passed, "sdk_operations": 3, "request": kwargs,
                    "results": results, "server_command": command,
                }, indent=2, ensure_ascii=False) + "\n")
                print(json.dumps({"passed": passed, "results": results}, ensure_ascii=False))
                return 0 if passed else 1
            finally:
                stop_server(server)


if __name__ == "__main__":
    raise SystemExit(main())
