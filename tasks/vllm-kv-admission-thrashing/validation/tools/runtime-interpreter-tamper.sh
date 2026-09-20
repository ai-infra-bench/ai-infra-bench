#!/usr/bin/env bash
set -euo pipefail

if ln -sf /bin/true /usr/local/bin/python 2>/tmp/python-tamper-error.log; then
  echo "unexpectedly replaced the system interpreter" >&2
  exit 1
fi

test -s /tmp/python-tamper-error.log
touch /workspace/vllm/vllm/runtime_tamper_attempted.py
