#!/usr/bin/env bash
set -euo pipefail
cd /workspace/vllm
git apply --check --unidiff-zero /solution/oracle.patch
git apply --whitespace=nowarn --unidiff-zero /solution/oracle.patch
