#!/usr/bin/env bash
# Verifier for vllm-trimmed-video-frame-sampling.
# The parent (root) builds fixtures with the ffmpeg CLI, extracts Base from the
# checkout's Git objects, and judges results; it never imports vLLM. Candidate
# and Base vLLM code run only in worker subprocesses as "nobody", which cannot
# modify the root-owned fixtures or verifier code. Each worker's process group
# is killed before pytest writes the JUnit report and before this script writes
# the reward, and every process of that user is killed after each worker (even
# ones that left the group). Base runs first and its output is sealed root-owned
# before candidate code runs. Status and JUnit stay in the root-owned work dir
# until grading ends; the parent alone writes /logs/verifier.
# Not protected: the agent runs as root in this same container before grading,
# so it could alter what the parent itself relies on (the Python installation
# and its .pth/sitecustomize hooks, the ffmpeg binaries, or the Git objects Base
# is extracted from). That is inherent to grading inside the agent's container.
set -uo pipefail
LOGS=/logs/verifier
mkdir -p "$LOGS"
rm -f "$LOGS"/reward.txt "$LOGS"/reward.json "$LOGS"/result.txt "$LOGS"/junit.xml "$LOGS"/status.json
BASE_COMMIT=11baa0ebd88480b0a3e30138e4ee189420cd33be
REPO=/workspace/vllm
WORK=$(mktemp -d /tmp/trimmed-video-verifier.XXXXXX)
chmod 755 "$WORK"
# Status lives in the root-owned work dir until grading ends, then is copied out.
STATUS="$WORK/status.json"
export VERIFIER_WORK="$WORK" VERIFIER_STATUS="$STATUS"

finish() {
  # $1 reward, $2 classification
  # Harbor parses every reward.json value as a number; the text label goes to result.txt.
  # Exit codes are -1 when that step did not run.
  local behavior=0 infra=0
  [ "$2" = behavior_failure ] && behavior=1
  [ "$2" = infrastructure_error ] && infra=1
  printf '%s\n' "$1" > "$LOGS/reward.txt"
  printf '%s\n' "$2" > "$LOGS/result.txt"
  printf '{"reward":%s,"behavior_failure":%s,"infrastructure_error":%s,"pytest_exit_code":%s,"junit_exit_code":%s}\n' \
    "$1" "$behavior" "$infra" "${pytest_rc:--1}" "${junit_rc:--1}" > "$LOGS/reward.json"
  cp "$STATUS" "$LOGS/status.json" 2>/dev/null || true
  cp "$WORK/junit.xml" "$LOGS/junit.xml" 2>/dev/null || true
  cp "$WORK"/worker-*.log "$LOGS"/ 2>/dev/null || true
  chmod -R a+rX "$LOGS" 2>/dev/null || true
  exit 0
}

# Pristine Base for differential references, from content-addressed objects.
BASE_ROOT="$WORK/base-vllm"
mkdir -p "$BASE_ROOT"
if ! GIT_NO_REPLACE_OBJECTS=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 \
    git -C "$REPO" -c safe.directory="$REPO" archive --format=tar "$BASE_COMMIT" vllm \
    | tar -x -C "$BASE_ROOT"; then
  printf '{"infrastructure_error":"Base commit objects unavailable in %s"}\n' "$REPO" > "$STATUS"
  finish 0 infrastructure_error
fi
chmod -R a+rX "$BASE_ROOT"
export BASE_VLLM_ROOT="$BASE_ROOT" CANDIDATE_VLLM_ROOT="$REPO"

if command -v setpriv >/dev/null && id nobody >/dev/null 2>&1; then
  export WORKER_PREFIX="setpriv --reuid=nobody --regid=nogroup --clear-groups --inh-caps=-all --"
else
  printf '{"infrastructure_error":"setpriv or user nobody unavailable"}\n' > "$STATUS"
  finish 0 infrastructure_error
fi

cp /tests/*.py "$WORK"/ && chmod 644 "$WORK"/*.py
pytest_rc=0
(cd "$WORK" && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH="$WORK" timeout 5400 \
  python -P -m pytest --noconftest -c /dev/null --rootdir="$WORK" -p no:cacheprovider \
    -q -rfE --junitxml="$WORK/junit.xml" "$WORK/test_trimmed_video.py") \
  > "$LOGS/pytest.log" 2>&1 || pytest_rc=$?
tail -n 60 "$LOGS/pytest.log"
junit_rc=0
python -P "$WORK/check_junit.py" "$WORK/junit.xml" || junit_rc=$?

if [ "$pytest_rc" -eq 0 ] && [ "$junit_rc" -eq 0 ]; then
  finish 1 passed
fi
if [ -f "$STATUS" ] && grep -q '"infrastructure_error"' "$STATUS"; then
  finish 0 infrastructure_error
fi
finish 0 behavior_failure
