#!/usr/bin/env bash
set -uo pipefail

export PYTHONPATH=/probe:/tests
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1

# Diagnostic run: nonzero pytest status records incompatibilities, not reward.
pytest --noconftest -c /dev/null --rootdir=/tests \
  --basetemp=/logs/python-current \
  -p no:cacheprovider -p pytest_asyncio.plugin -p pytest_plugin \
  -v --tb=short --junitxml=/logs/python-current.xml \
  /tests/test_sdk_fixture.py \
  /tests/test_rust_sdk_matrix.py \
  /tests/test_rust_request_matrix.py \
  /tests/test_rust_historical_regressions.py \
  /tests/test_real_qwen_backend.py
