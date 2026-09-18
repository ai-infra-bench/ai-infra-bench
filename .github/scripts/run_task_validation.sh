#!/usr/bin/env bash
set -euo pipefail

: "${TASK_NAME:?TASK_NAME is required}"
: "${TARGET_PLATFORM:?TARGET_PLATFORM is required}"
: "${PUBLISH_IMAGE:=false}"
: "${HARBOR_JOBS_DIR:=${GITHUB_WORKSPACE:-$PWD}/harbor-jobs}"

# GitHub Actions treats differently cased env names as duplicate YAML keys.
# Normalize the lowercase job values for tools that read uppercase proxy vars.
http_proxy_value="${http_proxy:-${HTTP_PROXY:-}}"
https_proxy_value="${https_proxy:-${HTTPS_PROXY:-}}"
no_proxy_value="${no_proxy:-${NO_PROXY:-}}"
if [[ -n "$http_proxy_value" ]]; then
  export http_proxy="$http_proxy_value" HTTP_PROXY="$http_proxy_value"
fi
if [[ -n "$https_proxy_value" ]]; then
  export https_proxy="$https_proxy_value" HTTPS_PROXY="$https_proxy_value"
fi
if [[ -n "$no_proxy_value" ]]; then
  export no_proxy="$no_proxy_value" NO_PROXY="$no_proxy_value"
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

task_dir="tasks/$TASK_NAME"
test -f "$task_dir/task.toml"

python3 .github/scripts/task_ci.py validate "$TASK_NAME"
python3 .github/scripts/task_ci.py hardware-check --task "$TASK_NAME"

gpu_count="$(python3 - "$task_dir/task.toml" <<'PY'
import sys, tomllib
with open(sys.argv[1], "rb") as stream:
    print(tomllib.load(stream)["environment"].get("gpus", 0) or 0)
PY
)"
harbor_command=(harbor)
harbor_environment=docker
if (( gpu_count > 0 )); then
  : "${AI_INFRA_GPU_POOL_CONFIG:?GPU runners require a host-managed pool configuration}"
  harbor_command=(python3 "$repo_root/.github/scripts/gpu_pool.py" --count "$gpu_count" -- harbor)
  harbor_environment=ci_gpu_docker:LeasedGpuDockerEnvironment
  export PYTHONPATH="$repo_root/.github/scripts${PYTHONPATH:+:$PYTHONPATH}"
fi

environment_key="$(
  python3 .github/scripts/task_ci.py env-key \
    --task "$TASK_NAME" \
    --platform "$TARGET_PLATFORM"
)"
cache_hit=false
if (( gpu_count > 0 )); then
  # Always rebuild on the local GPU runner. BuildKit reuses its persistent
  # local layers, while rebuilding ensures Dockerfile/environment changes can
  # never accidentally reuse a stale canonical image ID from task.toml.
  image_ref="ai-infra-bench-task-envs:${TASK_NAME}-${environment_key}"
else
  : "${GHCR_REPOSITORY:=ghcr.io/${GITHUB_REPOSITORY_OWNER}/ai-infra-bench-task-envs}"
  GHCR_REPOSITORY="$(printf '%s' "$GHCR_REPOSITORY" | tr '[:upper:]' '[:lower:]')"
  image_ref="${GHCR_REPOSITORY}:${TASK_NAME}-${environment_key}"
  if docker pull "$image_ref"; then
    cache_hit=true
  fi
fi

if [[ "$cache_hit" == true ]]; then
  printf 'Using cached image %s\n' "$image_ref"
else
  if (( gpu_count > 0 )); then
    printf 'Building GPU image locally; BuildKit layers may be reused\n'
  else
    printf 'No cached image for %s; building locally\n' "$image_ref"
  fi
  test -f "$task_dir/environment/Dockerfile"
  if (( gpu_count > 0 )); then
    # Self-hosted runners can inherit a shared, unwritable ~/.docker/buildx.
    # Buildx state is client-side; keep it job-local without replacing the
    # Docker CLI config (which may hold registry credentials or contexts).
    export BUILDX_CONFIG="$(mktemp -d "${RUNNER_TEMP:-/tmp}/ai-infra-buildx.XXXXXX")"
  fi
  build_attempt=1
  while true; do
    build_log="$(mktemp "${RUNNER_TEMP:-/tmp}/ai-infra-build.XXXXXX.log")"
    set +e
    docker buildx build \
      --load \
      --network "${AI_INFRA_BUILD_NETWORK:-default}" \
      --build-arg HTTP_PROXY --build-arg HTTPS_PROXY \
      --build-arg http_proxy --build-arg https_proxy \
      --build-arg NO_PROXY --build-arg no_proxy \
      --progress=plain \
      --tag "$image_ref" \
      --file "$task_dir/environment/Dockerfile" \
      "$task_dir/environment" 2>&1 | tee "$build_log"
    build_status="${PIPESTATUS[0]}"
    set -e
    if (( build_status == 0 )); then
      rm -f "$build_log"
      break
    fi
    if (( build_attempt >= 3 )) || ! grep -Eiq \
      'GnuTLS recv error|OpenSSL SSL_(connect|read)|SSL routines::unexpected eof while reading|RPC failed; curl|fatal: early EOF|Could not resolve host|Temporary failure (in name resolution|resolving)|TLS handshake timeout|proxyconnect tcp|connection reset by peer|context deadline exceeded|dial tcp.*(i/o timeout|network is unreachable|connection refused)|failed to fetch anonymous token|Failed to fetch.*(Connection failed|Temporary failure)|500 Internal Server Error' \
      "$build_log"; then
      rm -f "$build_log"
      exit "$build_status"
    fi
    printf 'Build failed due to a transient network error; retrying (%d/3)\n' \
      "$((build_attempt + 1))"
    rm -f "$build_log"
    sleep "$((build_attempt * 5))"
    ((build_attempt += 1))
  done
fi

runtime_image="$image_ref"
if (( gpu_count == 0 )) && [[ "$cache_hit" == true ]]; then
  runtime_image="$(
    docker image inspect \
      --format '{{range .RepoDigests}}{{println .}}{{end}}' \
      "$image_ref" |
      grep -F "${GHCR_REPOSITORY}@" |
      head -n 1
  )"
  test -n "$runtime_image"
fi

python3 .github/scripts/task_ci.py image-check \
  --task "$TASK_NAME" \
  --image "$runtime_image"

mkdir -p "$HARBOR_JOBS_DIR/$TASK_NAME"
cases_json="$(python3 .github/scripts/task_ci.py cases --task "$TASK_NAME")"

while IFS= read -r case_json; do
  case_name="$(jq -er '.name' <<<"$case_json")"
  expected_reward="$(jq -er '.expected_reward' <<<"$case_json")"
  case_dir="$(mktemp -d "${RUNNER_TEMP:-/tmp}/ai-infra-case.XXXXXX")"
  agent="$(
    python3 .github/scripts/task_ci.py prepare-case \
      --task "$TASK_NAME" \
      --image "$runtime_image" \
      --case "$case_name" \
      --output "$case_dir"
  )"
  job_name="${TASK_NAME}--${case_name}"
  printf 'Running %s with agent=%s expected_reward=%s\n' \
    "$job_name" "$agent" "$expected_reward"

  "${harbor_command[@]}" run \
    --path "$case_dir" \
    --agent "$agent" \
    --env "$harbor_environment" \
    --jobs-dir "$HARBOR_JOBS_DIR/$TASK_NAME" \
    --job-name "$job_name" \
    --n-concurrent 1 \
    --cpus ignore \
    --memory ignore \
    --delete \
    --yes

  result_path="$HARBOR_JOBS_DIR/$TASK_NAME/$job_name/result.json"
  if ! python3 .github/scripts/task_ci.py check-result \
    --result "$result_path" \
    --expected-reward "$expected_reward"; then
    # A Harbor job can return zero even when its trial failed before producing
    # a reward. GPU runner artifacts are not uploaded, so report the actual
    # exception rather than leaving only "reward is None" in the CI log.
    python3 - "$HARBOR_JOBS_DIR/$TASK_NAME/$job_name" <<'PY'
import json
import pathlib
import sys

for result_path in sorted(pathlib.Path(sys.argv[1]).glob("*/result.json")):
    trial = json.loads(result_path.read_text())
    exception = trial.get("exception_info") or {}
    if exception:
        print(json.dumps({
            "trial": result_path.parent.name,
            "exception_type": exception.get("exception_type"),
            "exception_message": str(exception.get("exception_message", ""))[:8000],
        }), flush=True)
PY
    exit 1
  fi
done < <(jq -c '.[]' <<<"$cases_json")

published=false
if (( gpu_count == 0 )) && [[ "$cache_hit" == false && "$PUBLISH_IMAGE" == true ]]; then
  docker push "$image_ref"
  published=true
fi

digest=""
if (( gpu_count == 0 )) && [[ "$image_ref" == ghcr.io/* && ("$cache_hit" == true || "$published" == true) ]]; then
  digest="$(docker buildx imagetools inspect "$image_ref" --format '{{json .Manifest.Digest}}' | tr -d '"')"
fi

summary="$HARBOR_JOBS_DIR/$TASK_NAME/ci-summary.json"
jq -n \
  --arg task "$TASK_NAME" \
  --arg environment_key "$environment_key" \
  --arg image "$image_ref" \
  --arg digest "$digest" \
  --argjson cache_hit "$cache_hit" \
  --argjson published "$published" \
  --argjson cases "$cases_json" \
  '{
    task: $task,
    environment_key: $environment_key,
    image: $image,
    registry_digest: $digest,
    cache_hit: $cache_hit,
    published: $published,
    cases: $cases
  }' > "$summary"

cat "$summary"
