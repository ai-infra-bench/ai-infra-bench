#!/usr/bin/env bash
# Run one real-agent rollout of a task through Harbor, reusing a locally built image.
#
# Usage:
#   tools/local_agent_rollout.sh <task> <image> [model] [agent-timeout-multiplier] [agent]
#   SETUP_MULT (env, default 1.0): multiplier for the agent SETUP timeout, kept at 1.0 so
#   a slow first-time CLI install (e.g. grok as a non-root agent user) is not capped by the
#   agent-execution multiplier.
#   ROLLOUT_HARBOR_ARGS (env): extra `harbor run` arguments, word-split (no secrets: they are
#   logged), e.g. "--ak config=/path/codex-config.toml" for a custom codex model provider.
#   e.g. tools/local_agent_rollout.sh pi-background-processes ai-infra-bench/pi-background-processes:local \
#            claude-opus-5 0.05 claude-code
#
# Credentials are read from $ROLLOUT_ENV (default ~/.ai-infra-bench/rollout.env), a
# KEY=VALUE file that is sourced and never printed. For claude-code it needs either
#   ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN), optionally ANTHROPIC_BASE_URL, or
#   CLAUDE_CODE_OAUTH_TOKEN (from `claude setup-token`) plus CLAUDE_FORCE_OAUTH=1 to use
#   the Claude subscription; Harbor forwards both into the agent container.
#
# Proxy: when the host has HTTPS_PROXY/HTTP_PROXY set, the same proxy is forwarded into the
# agent container (127.0.0.1 rewritten to host.docker.internal), which is faster here than
# the VM's default route. Harbor's egress sidecar (gost transparent proxy with SNI sniffing)
# passes direct TLS to allowlisted hosts but hangs HTTP CONNECT to a proxy, so in proxy mode
# the rollout copy's task.toml is rewritten: environment baseline and agent phase "public"
# (no interception; traffic is governed by the host proxy's own rules) and verifier phase
# "no-network" (sidecar deny-all during verify, as in CI). ROLLOUT_USE_PROXY=0 keeps the
# task's own no-network policy and only allowlists the API host for direct egress;
# ROLLOUT_USE_PROXY=1 fails instead of falling back when no host proxy is configured;
# ROLLOUT_USE_PROXY=public makes the agent phase public with no proxy at all (hosts with
# unrestricted direct egress), verifier phase no-network as always.
#
# Direct mode: Harbor's --allow-agent-host turns the no-network agent phase into an
# allowlist holding only the model API host. Agent installation runs under the environment
# baseline, so npm/claude download hosts are allowed there; the shared verifier sees that
# baseline allowlist too. Prefer an image with the agent preinstalled (Harbor skips install
# when `claude` is already on PATH). Verification always unsets every provider key and runs
# PI_OFFLINE=1.
set -euo pipefail

TASK=${1:?task name}
IMAGE=${2:?image tag}
MODEL=${3:-claude-opus-5}   # "default" leaves the model choice to the agent CLI
MODEL_ARGS=(); [ "$MODEL" != default ] && MODEL_ARGS=(--model "$MODEL")
MULT=${4:-0.05}
AGENT=${5:-claude-code}
ROLLOUT_ENV=${ROLLOUT_ENV:-$HOME/.ai-infra-bench/rollout.env}
SCRATCH=${AI_INFRA_SCRATCH:-$HOME/ai-infra-scratch}   # colima shares only $HOME
HARBOR_VERSION=${HARBOR_VERSION:-0.22.0}
REPO=$(cd "$(dirname "$0")/.." && pwd)

# shellcheck source=/dev/null
if [ -f "$ROLLOUT_ENV" ]; then set -a; . "$ROLLOUT_ENV"; set +a; fi
case "$AGENT" in
  *grok_build_oauth*)
    # Custom agent (tools/harbor_agents/grok_build_oauth.py): reuses the host's grok login.
    [ -f "${GROK_AUTH_JSON:-$HOME/.grok/auth.json}" ] || { echo "no grok session: run 'grok login' first" >&2; exit 2; } ;;
  *)
    if [ -z "${ANTHROPIC_API_KEY:-}${ANTHROPIC_AUTH_TOKEN:-}${CLAUDE_CODE_OAUTH_TOKEN:-}${OPENAI_API_KEY:-}${XAI_API_KEY:-}" ]; then
      echo "no provider credential found in $ROLLOUT_ENV" >&2; exit 2
    fi ;;
esac

# Model API host: used for the direct-egress allowlist and for the proxy reachability probe.
case "$AGENT" in
  claude-code) API_HOST=api.anthropic.com; BASE_URL=${ANTHROPIC_BASE_URL:-} ;;
  codex)       API_HOST=api.openai.com;    BASE_URL=${OPENAI_BASE_URL:-} ;;
  grok-build|*grok_build_oauth*) API_HOST=api.x.ai; BASE_URL=${XAI_BASE_URL:-} ;;
  *)           API_HOST=${ROLLOUT_API_HOST:?set ROLLOUT_API_HOST for agent $AGENT}; BASE_URL= ;;
esac
if [ -n "$BASE_URL" ]; then
  API_HOST=$(printf '%s' "$BASE_URL" | sed -E 's#^[a-z]+://##; s#[/:].*$##')
fi

# Host checks (docker VM clock, platform notes): an unreliable VM clock makes timing cases of
# the verifier fail at random, which would be read as the agent's failure.
bash "$REPO/tools/local_preflight.sh" "$IMAGE" || { rc=$?; [ "$rc" = 3 ] && exit 3; }

# Proxy decision (see header).
PROXY_ARGS=()
USE_PROXY=${ROLLOUT_USE_PROXY:-auto}
HOST_PROXY=${HTTPS_PROXY:-${https_proxy:-${HTTP_PROXY:-${http_proxy:-}}}}
if [ "$USE_PROXY" = auto ]; then
  if [ -n "$HOST_PROXY" ]; then USE_PROXY=1; else USE_PROXY=0; echo "network: no host proxy configured, using direct egress"; fi
fi
if [ "$USE_PROXY" = public ]; then
  # A host with unrestricted direct egress (e.g. a Linux dev box): agent phase public
  # without any proxy, verifier phase no-network. Needed for agents whose installer fetches
  # from hosts the direct-mode allowlist does not name.
  echo "network: no proxy; agent phase public, verifier phase no-network"
  HOST_ARGS=()
elif [ "$USE_PROXY" = 1 ]; then
  [ -n "$HOST_PROXY" ] || { echo "proxy requested but no HTTPS_PROXY/HTTP_PROXY on host" >&2; exit 2; }
  CT_PROXY=$(printf '%s' "$HOST_PROXY" | sed -E 's#127\.0\.0\.1|localhost#host.docker.internal#')
  PROXY_IP=$(docker run --rm "$IMAGE" sh -c 'getent hosts host.docker.internal | cut -d" " -f1')
  [ -n "$PROXY_IP" ] || { echo "cannot resolve host.docker.internal inside the image" >&2; exit 2; }
  docker run --rm -e "HTTPS_PROXY=$CT_PROXY" "$IMAGE" sh -c "curl -sS -m 15 -o /dev/null https://$API_HOST/" \
    || { echo "proxy $CT_PROXY cannot reach $API_HOST from a container" >&2; exit 2; }
  CT_NO_PROXY="localhost,127.0.0.1,::1,host.docker.internal,$PROXY_IP${NO_PROXY:+,$NO_PROXY}"
  echo "network: forwarding proxy $CT_PROXY (host $PROXY_IP) into the agent; agent phase public, verifier phase no-network"
  PROXY_ARGS=(--ae "HTTPS_PROXY=$CT_PROXY" --ae "HTTP_PROXY=$CT_PROXY" --ae "https_proxy=$CT_PROXY" --ae "http_proxy=$CT_PROXY" \
              --ae "NO_PROXY=$CT_NO_PROXY" --ae "no_proxy=$CT_NO_PROXY")
  HOST_ARGS=()
else
  HOST_ARGS=(--allow-agent-host "$API_HOST" --allow-environment-host registry.npmjs.org --allow-environment-host downloads.claude.ai)
fi

# Task copy whose Dockerfile is just FROM <image>; validation/ and lock files are not needed.
ROLL="$SCRATCH/rollout-task/$TASK"
rm -rf "$ROLL"; mkdir -p "$(dirname "$ROLL")"
cp -R "$REPO/tasks/$TASK" "$ROLL"
printf 'FROM %s\n' "$IMAGE" > "$ROLL/environment/Dockerfile"
rm -rf "$ROLL/validation" "$ROLL/environment/lock" "$ROLL/environment/baseline_check.py" "$ROLL/environment/image-manifest.json"
if [ "$USE_PROXY" = 1 ] || [ "$USE_PROXY" = public ]; then
  python3 - "$ROLL/task.toml" <<'PY'
import re, sys
path = sys.argv[1]
text = open(path).read()

def set_mode(text, section, mode):
    match = re.search(rf'(?ms)^\[{section}\]\n.*?(?=^\[|\Z)', text)
    assert match, f"missing [{section}] in task.toml"
    seg = match.group(0)
    if re.search(r'(?m)^network_mode\s*=', seg):
        new = re.sub(r'(?m)^network_mode\s*=.*$', f'network_mode = "{mode}"', seg)
    else:
        new = seg.rstrip('\n') + f'\nnetwork_mode = "{mode}"\n\n'
    return text.replace(seg, new)

text = set_mode(text, 'environment', 'public')
text = set_mode(text, 'agent', 'public')
text = set_mode(text, 'verifier', 'no-network')
open(path, 'w').write(text)
PY
  echo "rollout task.toml network policy:"; grep -nE '^\[|network_mode' "$ROLL/task.toml"
fi

STAMP=$(date +%Y%m%d-%H%M%S)
JOBS="$SCRATCH/harbor-jobs/rollouts"
AGENT_TAG=$(printf '%s' "$AGENT" | sed -E 's#^.*[:.]##' | tr '/:' '__')
JOB="$TASK--$AGENT_TAG--$(printf '%s' "$MODEL" | tr '/:' '__')--x$MULT--$STAMP"
mkdir -p "$JOBS"
echo "job: $JOBS/$JOB"
AUTH_MODE=api-key; [ "$AGENT" = claude-code ] && [ "${CLAUDE_FORCE_OAUTH:-0}" != 0 ] && AUTH_MODE=subscription-oauth
echo "agent=$AGENT model=$MODEL auth=$AUTH_MODE api_host=$API_HOST agent_timeout_multiplier=$MULT"

PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}" uvx --from "harbor==$HARBOR_VERSION" harbor run \
  --path "$ROLL" --agent "$AGENT" ${MODEL_ARGS[@]+"${MODEL_ARGS[@]}"} --env docker \
  --jobs-dir "$JOBS" --job-name "$JOB" --n-concurrent 1 \
  --cpus ignore --memory ignore \
  --agent-timeout-multiplier "$MULT" \
  --agent-setup-timeout-multiplier "${SETUP_MULT:-1.0}" \
  ${HOST_ARGS[@]+"${HOST_ARGS[@]}"} \
  ${PROXY_ARGS[@]+"${PROXY_ARGS[@]}"} \
  ${ROLLOUT_HARBOR_ARGS:-} \
  --yes 2>&1 | tee "$JOBS/$JOB.harbor.log" | grep -vE "ANTHROPIC_API_KEY|AUTH_TOKEN|OPENAI_API_KEY|OAUTH_TOKEN" || true

RESULT="$JOBS/$JOB/result.json"
if [ -f "$RESULT" ]; then
  python3 - "$RESULT" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print("stats:", json.dumps(d.get("stats", {}), indent=1)[:800])
PY
else
  echo "no result.json at $RESULT" >&2; exit 1
fi
