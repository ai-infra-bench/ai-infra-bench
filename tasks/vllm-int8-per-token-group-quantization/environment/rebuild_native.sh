#!/usr/bin/env bash
set -euo pipefail

repo=/workspace/repo
cd "${repo}"

# Rebuild native extensions for verification
python3 -m pip install --no-build-isolation --no-deps -e .
