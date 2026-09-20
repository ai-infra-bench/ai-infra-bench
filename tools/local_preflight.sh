#!/usr/bin/env bash
# Host checks before a local matrix or real-agent rollout. Sourced or run by
# tools/local_task_validation.py and tools/local_agent_rollout.sh.
#
#   tools/local_preflight.sh <image>
#
# 1. Docker VM clock. On macOS the colima/lima (vz) guest counter can run ~1.4% fast; the
#    lima guest agent then steps the guest wall clock back 100-200 ms every ~10 s. Any
#    program that mixes Date.now() with a monotonic clock (OpenTelemetry's anchored clock,
#    several pi-agent-trace submissions) then produces out-of-order timestamps, and a correct
#    submission fails timing cases at random. Measured here inside <image>; when the clocks
#    disagree and colima is in use, the stepping is stopped (`systemctl stop lima-guestagent`
#    in the VM; docker.sock and outbound traffic keep working; `colima restart` undoes it).
#    Exit 3 if the clocks still disagree. PREFLIGHT_SKIP_CLOCK=1 skips this check.
# 2. Platform notes (never fatal). A non-Linux host does not enforce file ownership on bind
#    mounts (/logs is one): an unprivileged uid can overwrite a root-owned file there, so
#    verifiers must keep reports and the reward in a container-local root-owned directory
#    until grading is over. An arm64 host cannot validate tasks whose verifier is pinned to
#    linux/amd64 (pi-safe-file-rollback).
set -u
IMAGE=${1:?image}
note() { echo "preflight: $*"; }

host_os=$(uname -s); host_arch=$(uname -m)
if [ "$host_os" != Linux ]; then
  note "host is $host_os: bind mounts such as /logs do not enforce file ownership here; a verifier that writes its reward straight into /logs/verifier is not protected locally (CI on Linux is)."
fi
img_arch=$(docker image inspect "$IMAGE" --format '{{.Architecture}}' 2>/dev/null || echo unknown)
case "$host_arch/$img_arch" in
  arm64/amd64|aarch64/amd64) note "image is amd64 on an arm64 host: it runs emulated (slow; ptrace-based verifiers do not work under emulation)." ;;
  arm64/arm64|aarch64/arm64) note "arm64 image: results of verifiers pinned to linux/amd64 builds are not meaningful here." ;;
esac

[ "${PREFLIGHT_SKIP_CLOCK:-0}" = 1 ] && exit 0
measure() {
  docker run --rm --entrypoint node "$IMAGE" -e 'const a=Date.now(),h=process.hrtime.bigint();setTimeout(()=>{console.log(Math.abs(a+Number(process.hrtime.bigint()-h)/1e6-Date.now()).toFixed(1))},13000)' 2>/dev/null
}
drift=$(measure)
if [ -z "$drift" ]; then note "clock check skipped (no node in $IMAGE)"; exit 0; fi
note "docker VM clock: monotonic vs wall clock differ by ${drift} ms over 13 s"
if awk "BEGIN{exit !($drift > 5)}"; then
  if command -v colima >/dev/null 2>&1 && colima status >/dev/null 2>&1; then
    note "clocks disagree; stopping lima-guestagent's clock stepping in the colima VM"
    colima ssh -- sudo systemctl stop lima-guestagent >/dev/null 2>&1 || true
    sleep 2; drift=$(measure); note "after the fix: ${drift:-?} ms"
  fi
  if [ -z "$drift" ] || awk "BEGIN{exit !($drift > 5)}"; then
    note "the docker VM clock is unreliable; timing-sensitive cases would fail at random. Fix the VM or set PREFLIGHT_SKIP_CLOCK=1."
    exit 3
  fi
fi
exit 0
