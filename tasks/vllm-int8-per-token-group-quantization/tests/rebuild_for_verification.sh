#!/usr/bin/env bash
# Build the public _C extension with the project's existing build_ext backend.
# The complete pip build remains available to solvers in the image.
set -euo pipefail

exec python3 -I /tests/build_native.py
