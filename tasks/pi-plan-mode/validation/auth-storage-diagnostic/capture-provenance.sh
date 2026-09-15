#!/usr/bin/env bash
set -euo pipefail
container=${1:?Usage: capture-provenance.sh CONTAINER}
printf 'captured_at=%s\n' "$(date -u +%FT%TZ)"
printf 'base_commit=d981de1229ef899957bbe968bc8dcda02a21f477\n'
printf 'container_state='
docker inspect "$container" --format '{{.State.Status}}'
printf 'image_id='
docker inspect "$container" --format '{{.Image}}'
printf 'network='
docker inspect "$container" --format '{{.HostConfig.NetworkMode}}'
printf 'nanocpus='
docker inspect "$container" --format '{{.HostConfig.NanoCpus}}'
printf 'memory_bytes='
docker inspect "$container" --format '{{.HostConfig.Memory}}'
for source_path in /workspace/pi/packages/coding-agent/test/auth-storage.test.ts /workspace/pi/packages/coding-agent/src/core/auth-storage.ts /workspace/pi/packages/coding-agent/src/utils/paths.ts /workspace/pi/packages/coding-agent/dist/utils/paths.js /diagnostic/drop_worker.cjs; do
  source_digest=$(docker cp "$container:$source_path" - | tar -xOf - | sha256sum)
  printf '%s %s\n' "${source_digest%% *}" "$source_path"
done
