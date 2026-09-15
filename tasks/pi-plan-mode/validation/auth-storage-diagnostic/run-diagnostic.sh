#!/usr/bin/env bash
set -uo pipefail
out=/tmp/pi-authstorage-fs-diagnostic-20260915-infra
container=pi-authstorage-fs-diagnostic-20260915
image=sha256:a68c346850d3b3ec045dd52aaf751e229e888ca365de99ab06a99fe88eeb0cda
mkdir -p "$out/results"
docker run -d --name "$container" --network none --cpus 4 --memory 8g \
  --volume "$out/revision-probe.mjs:/diagnostic/revision-probe.mjs:ro" \
  --volume /data00/home/xingjunqian/harbor-workspace/pi-plan-mode/verifier-debug/tests/drop_worker.cjs:/diagnostic/drop_worker.cjs:ro \
  --volume "$out/results:/diagnostic/results" \
  --workdir /workspace/pi/packages/coding-agent --entrypoint /bin/bash "$image" -lc 'sleep infinity' > "$out/results/container-id.txt"
docker inspect "$container" > "$out/results/container-inspect.json"
docker exec "$container" bash -lc 'mkdir -p /tmp/authdiag-overlay /dev/shm/authdiag-tmpfs && chmod 1777 /tmp/authdiag-overlay /dev/shm/authdiag-tmpfs'
docker exec --user 65534:65534 "$container" node /diagnostic/revision-probe.mjs > "$out/results/revision-probe.jsonl" 2> "$out/results/revision-probe.stderr"
printf '%s\n' "$?" > "$out/results/revision-probe.exit"
for round in 1 2 3 4 5; do
  if (( round % 2 )); then filesystems=(overlay tmpfs); else filesystems=(tmpfs overlay); fi
  for fs in "${filesystems[@]}"; do
    if [ "$fs" = overlay ]; then candidate_tmpdir=/tmp/authdiag-overlay; else candidate_tmpdir=/dev/shm/authdiag-tmpfs; fi
    name="auth-storage-${fs}-${round}"
    docker exec -e TMPDIR="$candidate_tmpdir" -e NODE_OPTIONS=--require=/diagnostic/drop_worker.cjs -e NO_COLOR=1 -e FORCE_COLOR=0 "$container" \
      node ../../node_modules/vitest/vitest.mjs run --pool=forks --maxWorkers=4 --retry=0 --reporter=junit \
      --outputFile="/diagnostic/results/${name}.xml" test/auth-storage.test.ts \
      > "$out/results/${name}.log" 2>&1
    status=$?
    printf '%s\n' "$status" > "$out/results/${name}.exit"
    printf '%s exit=%s\n' "$name" "$status"
  done
done
docker stop --timeout 5 "$container" > "$out/results/container-stop.txt"
