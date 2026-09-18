#!/bin/bash
set -euo pipefail
cd /workspace/repo
test "$(id -un)" = agent
test "$(git rev-parse HEAD)" = c7560af42487b1570c4e6f4cea5df1605a4d59fc
test -z "$(git status --porcelain)"
test -z "$(git remote)"
test "$(git rev-list --all --count)" -eq 1
.venv/bin/python - <<'PY'
import importlib.metadata as m
import importlib.util
import pathlib
import sys
import torch
import vllm
assert sys.prefix == '/workspace/repo/.venv'
assert pathlib.Path(vllm.__file__).is_relative_to('/workspace/repo')
assert pathlib.Path(importlib.util.find_spec('vllm._C').origin).is_relative_to('/workspace/repo')
system = {d.metadata['Name'].lower().replace('_','-'): d.version for d in m.distributions(path=['/usr/local/lib/python3.12/site-packages'])}
for d in m.distributions(path=['/workspace/repo/.venv/lib/python3.12/site-packages']):
    name=d.metadata['Name'].lower().replace('_','-')
    if name in system:
        assert d.version == system[name], (name, d.version, system[name])
print('Runtime versions preserved:', torch.__version__, 'source:', vllm.__file__)
PY
.venv/bin/pre-commit install-hooks
.venv/bin/python -m pytest tests/config/test_config_utils.py -q
.venv/bin/pre-commit run --files tests/config/test_config_utils.py
.venv/bin/shellcheck --version
go version
# A real lint failure proves the cached hook is executing, not merely present.
trap 'rm -f offline_lint_probe.py' EXIT
cat > offline_lint_probe.py <<'PY'
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
print(undefined_offline_probe)
PY
if .venv/bin/pre-commit run ruff-check --files offline_lint_probe.py > /tmp/offline-lint-output.txt 2>&1; then
    echo 'ruff failed to reject an undefined name' >&2
    exit 1
fi
cat /tmp/offline-lint-output.txt
grep -q F821 /tmp/offline-lint-output.txt
rm offline_lint_probe.py
trap - EXIT
test -z "$(git status --porcelain)"
echo 'OFFLINE_DEVELOPER_SMOKE_PASSED'
