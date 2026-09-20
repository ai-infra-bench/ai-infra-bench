#!/bin/bash
set -euo pipefail
solution_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd /workspace/pi
git apply "$solution_dir/implementation.patch"
cp "$solution_dir/team.ts" "$solution_dir/team-worker.ts" packages/coding-agent/examples/extensions/subagent/
