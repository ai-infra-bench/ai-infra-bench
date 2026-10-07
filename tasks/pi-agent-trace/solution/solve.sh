#!/usr/bin/env bash
set -euo pipefail
cd /workspace/pi
git apply --check /solution/oracle.patch
git apply --whitespace=nowarn /solution/oracle.patch
