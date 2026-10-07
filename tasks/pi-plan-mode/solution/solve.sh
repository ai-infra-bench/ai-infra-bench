#!/usr/bin/env bash
set -euo pipefail
cd /workspace/pi
test "$(git rev-parse HEAD)" = d981de1229ef899957bbe968bc8dcda02a21f477
git apply --check /solution/oracle.patch
git apply /solution/oracle.patch
