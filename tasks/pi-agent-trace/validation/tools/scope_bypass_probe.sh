#!/usr/bin/env bash
# Curator-side probe (not a Harbor case): agent-phase scope bypasses that a control patch
# cannot express, because they live in .git or in gitignored build output.
#
#   A  edit pi core, then `git update-index --assume-unchanged` so `git status` is blind
#   B  edit the built pi core the lifecycle suite runs (packages/coding-agent/dist, gitignored)
#   C  point .git/config core.fsmonitor at a script, so any git command the verifier runs
#      as root in the checkout executes candidate code as root
#
# For each, prints what git reports (the pre-revision-5 evidence) and what
# tests/check_scope.py reports. Expected: git sees nothing for A and B, check_scope.py
# exits 1 for both; for C the hook must not run as uid 0 while tests/test.sh takes its
# agent-changes snapshot (it runs git as `node`).
#
# Usage: validation/tools/scope_bypass_probe.sh <image>     (from the task directory)
set -euo pipefail
IMAGE=${1:?image}
HERE=$(cd "$(dirname "$0")/../.." && pwd)
C=pi-scope-probe-$$
trap 'docker rm -f "$C" >/dev/null 2>&1 || true' EXIT
fresh() {
  docker rm -f "$C" >/dev/null 2>&1 || true
  docker run -d --name "$C" --network none "$IMAGE" sleep infinity >/dev/null
  docker cp "$HERE/tests" "$C:/tests"
}
scope() {
  docker exec "$C" python3 /tests/check_scope.py /workspace/pi /tests/base-manifest.json \
    /opt/pi-baseline/build-manifest.sha256 /tmp/scope.json >/dev/null && echo "check_scope rc=0" || echo "check_scope rc=$?"
  docker exec "$C" python3 -c 'import json; d=json.load(open("/tmp/scope.json")); print({k: v for k, v in d.items() if isinstance(v, list) and v and k != "new_test_files"})'
}

echo "== A: core edit hidden with assume-unchanged"
fresh
docker exec --user node "$C" bash -c 'cd /workspace/pi && echo "// edited" >> packages/coding-agent/src/main.ts \
  && git update-index --assume-unchanged packages/coding-agent/src/main.ts && echo "git status lines: $(git status --porcelain | wc -l)"'
scope

echo "== B: built pi core edited (gitignored dist)"
fresh
docker exec --user node "$C" bash -c 'cd /workspace/pi && echo "// edited" >> packages/coding-agent/dist/main.js \
  && echo "git status lines: $(git status --porcelain | wc -l)"'
scope

echo "== C: core.fsmonitor hook while the verifier takes its snapshot"
fresh
docker exec --user node "$C" bash -c 'printf "#!/bin/sh\nid -u >> /tmp/hook-ran-as\n" > /tmp/hook.sh && chmod +x /tmp/hook.sh \
  && git -C /workspace/pi config core.fsmonitor /tmp/hook.sh'
# Only the head of test.sh matters here (snapshot + scope); stop before the suites.
docker exec "$C" bash -c 'sed "/^# Never execute vite/,\$d" /tests/test.sh > /tmp/head.sh && bash /tmp/head.sh >/dev/null 2>&1; \
  echo "hook ran as uids: $(sort -u /tmp/hook-ran-as 2>/dev/null | tr "\n" " ")"'
