set -uo pipefail
export PI_WORKSPACE=/workspace/pi PI_OFFLINE=1 PI_TELEMETRY=0 PI_NO_LOCAL_LLM=1
export NODE_OPTIONS=--require=/tests/drop_worker.cjs PI_TRUSTED_TESTS=/tests
cd /workspace/pi/packages/coding-agent
mapfile -t old_tests < /tests/p2p-files.txt
started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
rc=0
node ../../node_modules/vitest/vitest.mjs run --pool=forks --retry=2 --maxWorkers=4 --reporter=junit --outputFile=/logs/verifier/base-full-junit.xml "${old_tests[@]}" >/logs/verifier/base-full.log 2>&1 || rc=$?
printf '{"started":"%s","finished":"%s","exit_code":%s}\n' "$started" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$rc" > /logs/verifier/base-full-run.json
