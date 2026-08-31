#!/usr/bin/env bash
set -euo pipefail

: "${TASK_NAME:?TASK_NAME is required}"
: "${TARGET_PLATFORM:?TARGET_PLATFORM is required}"
: "${PUBLISH_IMAGE:=false}"
: "${GHCR_REPOSITORY:=ghcr.io/${GITHUB_REPOSITORY_OWNER}/ai-infra-bench-task-envs}"
: "${HARBOR_JOBS_DIR:=${GITHUB_WORKSPACE:-$PWD}/harbor-jobs}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

task_dir="tasks/$TASK_NAME"
test -f "$task_dir/task.toml"

python3 .github/scripts/task_ci.py validate "$TASK_NAME"
python3 .github/scripts/task_ci.py hardware-check --task "$TASK_NAME"

environment_key="$(
  python3 .github/scripts/task_ci.py env-key \
    --task "$TASK_NAME" \
    --platform "$TARGET_PLATFORM"
)"
image_ref="${GHCR_REPOSITORY}:${TASK_NAME}-${environment_key}"
cache_hit=false

if docker pull "$image_ref"; then
  cache_hit=true
  printf 'Using cached image %s\n' "$image_ref"
else
  printf 'No cached image for %s; building locally\n' "$image_ref"
  test -f "$task_dir/environment/Dockerfile"
  docker buildx build \
    --load \
    --progress=plain \
    --tag "$image_ref" \
    --file "$task_dir/environment/Dockerfile" \
    "$task_dir/environment"
fi

runtime_image="$image_ref"
if [[ "$cache_hit" == true ]]; then
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

  harbor run \
    --path "$case_dir" \
    --agent "$agent" \
    --env docker \
    --jobs-dir "$HARBOR_JOBS_DIR/$TASK_NAME" \
    --job-name "$job_name" \
    --n-concurrent 1 \
    --cpus ignore \
    --memory ignore \
    --delete \
    --yes

  python3 .github/scripts/task_ci.py check-result \
    --result "$HARBOR_JOBS_DIR/$TASK_NAME/$job_name/result.json" \
    --expected-reward "$expected_reward"
done < <(jq -c '.[]' <<<"$cases_json")

published=false
if [[ "$cache_hit" == false && "$PUBLISH_IMAGE" == true ]]; then
  docker push "$image_ref"
  published=true
fi

digest=""
if [[ "$image_ref" == ghcr.io/* && ("$cache_hit" == true || "$published" == true) ]]; then
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
