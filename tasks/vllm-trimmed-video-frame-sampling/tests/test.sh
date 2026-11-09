#!/usr/bin/env bash
# Verifier for vllm-trimmed-video-frame-sampling.
# Trusted parent (root): builds fixtures with the ffmpeg CLI, extracts pristine
# Base from the checkout's Git objects, and judges results. Candidate and Base
# vLLM code only run in worker subprocesses as the unprivileged user "nobody".
set -uo pipefail
LOGS=/logs/verifier
mkdir -p "$LOGS"
rm -f "$LOGS"/reward.txt "$LOGS"/reward.json "$LOGS"/junit.xml "$LOGS"/status.json
BASE_COMMIT=11baa0ebd88480b0a3e30138e4ee189420cd33be
REPO=/workspace/vllm
WORK=$(mktemp -d /tmp/trimmed-video-verifier.XXXXXX)
chmod 755 "$WORK"
export VERIFIER_WORK="$WORK" VERIFIER_STATUS="$LOGS/status.json"

finish() {
  # $1 reward, $2 classification
  printf '%s\n' "$1" > "$LOGS/reward.txt"
  printf '{"reward":%s,"result":"%s","pytest_exit_code":%s,"junit_exit_code":%s}\n' \
    "$1" "$2" "${pytest_rc:-null}" "${junit_rc:-null}" > "$LOGS/reward.json"
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
  printf '{"infrastructure_error":"Base commit objects unavailable in %s"}\n' "$REPO" > "$LOGS/status.json"
  finish 0 infrastructure_error
fi
chmod -R a+rX "$BASE_ROOT"
export BASE_VLLM_ROOT="$BASE_ROOT" CANDIDATE_VLLM_ROOT="$REPO"

if command -v setpriv >/dev/null && id nobody >/dev/null 2>&1; then
  export WORKER_PREFIX="setpriv --reuid=nobody --regid=nogroup --clear-groups --inh-caps=-all --"
else
  printf '{"infrastructure_error":"setpriv or user nobody unavailable"}\n' > "$LOGS/status.json"
  finish 0 infrastructure_error
fi

cp /tests/*.py "$WORK"/ && chmod 644 "$WORK"/*.py
pytest_rc=0
(cd "$WORK" && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH="$WORK" timeout 5400 \
  python -P -m pytest --noconftest -c /dev/null --rootdir="$WORK" -p no:cacheprovider \
    -q -rfE --junitxml="$LOGS/junit.xml" "$WORK/test_trimmed_video.py") \
  > "$LOGS/pytest.log" 2>&1 || pytest_rc=$?
tail -n 60 "$LOGS/pytest.log"
junit_rc=0
python -P "$WORK/check_junit.py" "$LOGS/junit.xml" || junit_rc=$?

if [ "$pytest_rc" -eq 0 ] && [ "$junit_rc" -eq 0 ]; then
  finish 1 passed
fi
if [ -f "$LOGS/status.json" ] && grep -q '"infrastructure_error"' "$LOGS/status.json"; then
  finish 0 infrastructure_error
fi
finish 0 behavior_failure
