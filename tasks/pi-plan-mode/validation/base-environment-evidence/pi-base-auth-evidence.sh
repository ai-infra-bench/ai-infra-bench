#!/usr/bin/env bash
set -uo pipefail
export PI_WORKSPACE=/workspace/pi PI_OFFLINE=1 PI_TELEMETRY=0 PI_NO_LOCAL_LLM=1
export NODE_OPTIONS=--require=/tests/drop_worker.cjs PI_TRUSTED_TESTS=/tests
cd /workspace/pi/packages/coding-agent
{
  date -u +%Y-%m-%dT%H:%M:%SZ
  git rev-parse HEAD
  git status --porcelain
  sha256sum test/auth-storage.test.ts src/core/auth-storage.ts src/utils/paths.ts /tests/drop_worker.cjs
  printf '%s\n' 'node ../../node_modules/vitest/vitest.mjs run --pool=forks --retry=2 --maxWorkers=4 --reporter=junit --outputFile=/logs/verifier/base-auth-RUN-junit.xml test/auth-storage.test.ts'
} > /logs/verifier/provenance.txt
for run in 1 2 3 4 5; do
  started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  rc=0
  node ../../node_modules/vitest/vitest.mjs run --pool=forks --retry=2 --maxWorkers=4 --reporter=junit --outputFile="/logs/verifier/base-auth-$run-junit.xml" test/auth-storage.test.ts > "/logs/verifier/base-auth-$run.log" 2>&1 || rc=$?
  printf '{"run":%s,"started":"%s","finished":"%s","exit_code":%s}\n' "$run" "$started" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$rc" >> /logs/verifier/runs.jsonl
done
