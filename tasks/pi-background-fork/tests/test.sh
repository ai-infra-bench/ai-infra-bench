#!/usr/bin/env bash
# Verifier entrypoint. Runs pi's own suite (PASS_TO_PASS), the submission's unit
# tests, and the behavioral verifier (verify.py), which drives real pi processes
# against a scripted model endpoint. A successful process exit is never sufficient
# on its own: verify.py's root-written summary must list every case as passed.
#
# Trust boundary: the agent phase already runs as the unprivileged `node` user
# (task.toml [agent].user), but this script runs as root. Every step that
# executes candidate code -- the whole pi suite in PASS_TO_PASS, the candidate's
# new test file, and every pi process of the behavioral verifier (which loads the
# candidate extension, and the forks it starts) -- is run as `node`, so candidate
# code can never rewrite the root-owned test
# runner, interpreter or baseline that the scoring depends on, and never writes
# the reward file. Reports are produced by `node` into a node-owned scratch dir;
# root parses them and writes the reward. `node` processes are reaped between
# steps so nothing candidate-spawned can rewrite a report or the reward after
# the fact. (A candidate can still, in principle, tamper with the report of the
# suite it runs inside from within that same process; that is candidate-side
# cheating for the hack screen, not a runner/scorer substitution.)
#
# What the submission changed is decided by content, never by git: the checkout and
# its .git belong to the agent, so check_scope.py hashes the protected files against
# tests/base-manifest.json and the image's root-owned build manifest (see its docstring).
set -uo pipefail
# Reap agent-phase writers before changing ownership or touching old outputs.
reap_node() {
  pkill -9 -u node 2>/dev/null || true
  for _ in $(seq 1 100); do pgrep -u node >/dev/null 2>&1 || break; sleep 0.1; done
}
reap_node
umask 022
# Harbor may provide writable output mounts and pre-existing node-owned files.
# Establish the boundary explicitly, preserving already-open stdout files.
/usr/bin/python3 -I /tests/prepare_verifier_output.py || exit 2
if ! su -p node -s /bin/bash -c '/usr/bin/python3 -I /tests/prepare_verifier_output.py --check-not-writable'; then
  echo "verifier output isolation failed: candidate can still write an output path"
  exit 2
fi
rm -rf /logs/verifier/{reward.txt,reward.json,behavior,behavior.log,scope.log,scope-summary.json,candidate-tests-junit.xml}
export PI_WORKSPACE=/workspace/pi
export PI_VERIFIER_FIXTURES=/tests/fixtures
export PI_OFFLINE=1 PI_TELEMETRY=0 PI_NO_LOCAL_LLM=1
# Verification never contacts a real model. The image is no-network, but make it
# impossible anyway: drop every credential pi's env-api-keys.ts or pi-test.sh
# knows about, so key-gated suites stay skipped and no provider is configured.
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_OAUTH_TOKEN OPENAI_API_KEY GEMINI_API_KEY \
  GOOGLE_CLOUD_API_KEY GROQ_API_KEY CEREBRAS_API_KEY XAI_API_KEY OPENROUTER_API_KEY ZAI_API_KEY \
  ZAI_CODING_CN_API_KEY MISTRAL_API_KEY MINIMAX_API_KEY MINIMAX_CN_API_KEY AI_GATEWAY_API_KEY \
  OPENCODE_API_KEY COPILOT_GITHUB_TOKEN GH_TOKEN GITHUB_TOKEN HF_TOKEN DEEPSEEK_API_KEY \
  FIREWORKS_API_KEY KIMI_API_KEY MOONSHOT_API_KEY NVIDIA_API_KEY TOGETHER_API_KEY BASETEN_API_KEY \
  CLOUDFLARE_API_KEY RADIUS_API_KEY ANT_LING_API_KEY XIAOMI_API_KEY XIAOMI_TOKEN_PLAN_AMS_API_KEY \
  XIAOMI_TOKEN_PLAN_CN_API_KEY XIAOMI_TOKEN_PLAN_SGP_API_KEY QWEN_TOKEN_PLAN_API_KEY \
  QWEN_TOKEN_PLAN_CN_API_KEY AZURE_OPENAI_API_KEY AZURE_OPENAI_BASE_URL AZURE_OPENAI_RESOURCE_NAME \
  GOOGLE_APPLICATION_CREDENTIALS GOOGLE_CLOUD_PROJECT GCLOUD_PROJECT GOOGLE_CLOUD_LOCATION \
  AWS_PROFILE AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_REGION \
  AWS_DEFAULT_REGION AWS_BEARER_TOKEN_BEDROCK AWS_CONTAINER_CREDENTIALS_RELATIVE_URI \
  AWS_CONTAINER_CREDENTIALS_FULL_URI AWS_WEB_IDENTITY_TOKEN_FILE
# HOME must be writable by the `node` user that runs the suites (su -p keeps it).
export HOME=/tmp/pi-verifier-home
rm -rf "$HOME" && mkdir -p "$HOME" && chown node:node "$HOME"
# Node-owned scratch for the reports the suites produce; /logs/verifier stays
# root-only so the reward file is never candidate-writable.
VOUT=/tmp/pi-verifier-out
rm -rf "$VOUT" && mkdir -p "$VOUT" && chown node:node "$VOUT"

# Run a command as the unprivileged node user, preserving the verifier env
# (-p keeps HOME/PI_*/NODE_OPTIONS and the unset provider keys). exec so the
# timeout/kill lands on node, not on su.
as_node() { su -p node -s /bin/bash -c "cd /workspace/pi/packages/coding-agent && $*"; }

if ! cd /workspace/pi/packages/coding-agent; then
  echo "verifier: workspace /workspace/pi/packages/coding-agent is missing" | tee /logs/verifier/verifier-error.log
  printf '0\n' > /logs/verifier/reward.txt
  printf '{"reward":0,"command_exit_code":1,"error":"workspace missing"}\n' > /logs/verifier/reward.json
  exit 0
fi
# Nothing the agent phase left running may touch the workspace while it is judged.
reap_node
# The checkers, pins and manifests in /tests decide the reward; the candidate runs as
# `node` and must not be able to write them.
if su node -s /bin/bash -c 'test -w /tests || test -w /tests/test.sh || test -w /tests/verify.py || test -w /tests/fixture.ts || test -w /opt/pi-baseline'; then
  echo "verifier: /tests or /opt/pi-baseline is writable by the candidate user" | tee /logs/verifier/verifier-error.log
  printf '0\n' > /logs/verifier/reward.txt
  printf '{"reward":0,"command_exit_code":1,"error":"verifier files writable by candidate"}\n' > /logs/verifier/reward.json
  exit 0
fi

behavior_rc=0
behavior_integrity_rc=0
p2p_rc=0
p2p_check_rc=0
candidate_tests_rc=0

# What the agent changed is archived by the task's [[verifier.collect]] hook (solution.patch
# and the untracked files under /logs/artifacts), which runs as the agent user before the
# tests are uploaded. This script never runs git in the checkout: its .git/config belongs to
# the agent, and git executes what that config names (core.fsmonitor, diff.external, ...) as
# the caller, which here would be root.
# Scope: the instruction keeps the work inside the extension directory, a new unit test
# file and documentation, and forbids changes to pi core, to the build/test toolchain the
# verifier is about to execute, and to existing test files. Decided by content hashes
# (check_scope.py); scratch files elsewhere are not penalised. Bit 1: pi core, toolchain
# or built dist changed or added to. Bit 2: an existing test file changed. Bit 4: error.
scope_rc=0
tests_modified=0
run_scope_check() {
  local rc=0
  python3 /tests/check_scope.py /workspace/pi /tests/base-manifest.json \
    /opt/pi-baseline/build-manifest.sha256 "/logs/verifier/$1" > "/logs/verifier/${1%.json}.log" 2>&1 || rc=$?
  if [ $((rc & 13)) -ne 0 ]; then
    echo "SCOPE ($1): protected files changed, a required deliverable is missing, or the scope check failed:"
    cat "/logs/verifier/${1%.json}.log"
    scope_rc=1
  fi
  if [ $((rc & 2)) -ne 0 ]; then tests_modified=1; fi
}
# Not piped: a function in a pipeline runs in a subshell and scope_rc would be lost.
run_scope_check scope-summary.json > /logs/verifier/scope.log 2>&1
cat /logs/verifier/scope.log
# Never execute vite's transient config bundles left by the agent phase. The
# dirs live under root-owned node_modules, so node cannot recreate them; clear
# the contents and hand the empty dirs back to node for fresh temp bundles.
for d in /workspace/pi/node_modules/.vite-temp /workspace/pi/node_modules/.vite \
         /workspace/pi/packages/*/node_modules/.vite-temp /workspace/pi/packages/*/node_modules/.vite; do
  rm -rf "$d" 2>/dev/null || true
  mkdir -p "$d" 2>/dev/null && chown node:node "$d" 2>/dev/null || true
done

# PASS_TO_PASS: pi's own coding-agent suite must match the Base baseline recorded in the
# image, and existing test files must be untouched (new files are fine). Only the Base
# test files run here (named by the pinned baseline), so the scored report holds the Base
# inventory and nothing else; the submission's own test files run right after, on their
# own, and must pass (the instruction asks for a unit test file that runs with `npm test`).
if [ "$tests_modified" -ne 0 ]; then
  echo "PASS_TO_PASS: existing test files were modified" | tee /logs/verifier/pass-to-pass.log
  python3 -c 'import json,sys; print("\n".join(json.load(open(sys.argv[1]))["tests_modified"]))' /logs/verifier/scope-summary.json | tee -a /logs/verifier/pass-to-pass.log
  p2p_check_rc=1
elif ! python3 /tests/check_pass_to_pass.py --list-files /opt/pi-baseline/coding-agent-junit.xml /tests/baseline-pins.json > /tmp/pi-p2p-files.txt; then
  echo "PASS_TO_PASS: the image baseline does not match the pins" | tee /logs/verifier/pass-to-pass.log
  p2p_check_rc=1
else
  mapfile -t base_tests < /tmp/pi-p2p-files.txt
  as_node "exec timeout 900 node ../../node_modules/vitest/vitest.mjs run --retry 2 --maxWorkers=4 --reporter=junit --outputFile=$VOUT/pass-to-pass-junit.xml ${base_tests[*]}" \
    > /logs/verifier/pass-to-pass.log 2>&1 || p2p_rc=$?
  reap_node
  cp "$VOUT/pass-to-pass-junit.xml" /logs/verifier/pass-to-pass-junit.xml 2>/dev/null || true
  tail -n 20 /logs/verifier/pass-to-pass.log
  # The baseline is root-owned in the image; check_pass_to_pass.py also verifies it
  # against pins (Base case inventory, key-gated skipped set, failure cap) that hold
  # across image builds and platforms, so a rewritten baseline is rejected.
  python3 /tests/check_pass_to_pass.py /opt/pi-baseline/coding-agent-junit.xml /logs/verifier/pass-to-pass-junit.xml /tests/baseline-pins.json || p2p_check_rc=$?

  mapfile -t new_tests < <(python3 -c 'import json,sys; print("\n".join("/workspace/pi/" + p for p in json.load(open(sys.argv[1]))["new_test_files"]))' /logs/verifier/scope-summary.json)
  if [ "${#new_tests[@]}" -gt 0 ] && [ -n "${new_tests[0]}" ]; then
    printf -v quoted_new_tests '%q ' "${new_tests[@]}"
    as_node "exec timeout 600 node ../../node_modules/vitest/vitest.mjs run --retry 2 --maxWorkers=4 --reporter=junit --outputFile=$VOUT/candidate-tests-junit.xml ${quoted_new_tests}" \
      > /logs/verifier/candidate-tests.log 2>&1 || candidate_tests_rc=$?
    reap_node
    cp "$VOUT/candidate-tests-junit.xml" /logs/verifier/candidate-tests-junit.xml 2>/dev/null || true
    tail -n 20 /logs/verifier/candidate-tests.log
    python3 /tests/check_candidate_tests.py /logs/verifier/candidate-tests-junit.xml || candidate_tests_rc=1
  else
    candidate_tests_rc=1
    echo "candidate tests: the submission added no test file" | tee /logs/verifier/candidate-tests.log
  fi
fi

# Behavior: verify.py (root) serves the scripted model, starts every pi parent as `node`
# through run_as_node.py, and writes its reports into a root-only directory. Its exit
# code and summary are produced outside any candidate process.
reap_node
BOUT=/tmp/pi-fork-behavior
rm -rf "$BOUT"
timeout 1800 /usr/bin/python3 -I /tests/verify.py --output "$BOUT" > /logs/verifier/behavior.log 2>&1 || behavior_rc=$?
reap_node
cat /logs/verifier/behavior.log
cp -R "$BOUT" /logs/verifier/behavior 2>/dev/null || true
python3 -c '
import json, sys
sys.path.insert(0, "/tests")
import verify
s = json.load(open(sys.argv[1]))
ok = s["cases"] == verify.CASES and s["passed"] == verify.CASES and not s["failed"]
print("behavior summary:", "complete" if ok else "incomplete", json.dumps(s["failed"]))
sys.exit(0 if ok else 1)
' "$BOUT/summary.json" || behavior_integrity_rc=1

# Final reap so no candidate-spawned process can rewrite the reward after this point.
reap_node
# Candidate code ran inside the suites above as the owner of the checkout; a submission
# whose tests or extension rewrote pi core or the built dist during verification is
# rejected the same way as one that did it during the agent phase.
run_scope_check scope-summary-final.json >> /logs/verifier/scope.log 2>&1
cat /logs/verifier/scope.log
reward=0
if [ "$behavior_rc" -eq 0 ] && [ "$behavior_integrity_rc" -eq 0 ] \
   && [ "$p2p_check_rc" -eq 0 ] && [ "$candidate_tests_rc" -eq 0 ] && [ "$scope_rc" -eq 0 ]; then
  reward=1
fi
printf '%s\n' "$reward" > /logs/verifier/reward.txt
printf '{"reward":%s,"command_exit_code":%s,"behavior_exit_code":%s,"behavior_integrity_exit_code":%s,"pass_to_pass_exit_code":%s,"pass_to_pass_check_exit_code":%s,"candidate_tests_exit_code":%s,"scope_exit_code":%s}\n' \
  "$reward" "$((1-reward))" "$behavior_rc" "$behavior_integrity_rc" "$p2p_rc" "$p2p_check_rc" "$candidate_tests_rc" "$scope_rc" > /logs/verifier/reward.json
exit 0
