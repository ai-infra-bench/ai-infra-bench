#!/usr/bin/env bash
# Trusted scoring entry for vllm-moe-permute-batch-scaling.
#
# Boundary contract:
#   * reward defaults to 0; it is raised ONLY by a positively verified,
#     structurally complete scoring manifest (fail closed).
#   * root performs trusted orchestration ONLY. The candidate's CMake/build
#     runs as the unprivileged `agent` user, never as root.
#   * provenance collection uses a hermetic Git configuration: no user/system
#     config, no external diff/textconv helpers, no fsmonitor, no hooks path.
#   * the native artifact is frozen by root into a root-owned staging dir before
#     any candidate Python is imported; workers load ONLY that staged file.
#   * this script never imports candidate Python and never resolves the native
#     module via find_spec.
set -uo pipefail

mkdir -p /logs/verifier
printf '0\n' > /logs/verifier/reward.txt

REPO=/app
STAGE_MANIFEST=/logs/verifier/native-staging.json
SCORE_MANIFEST=/logs/verifier/scoring-manifest.json

fail_closed() {
  printf 'scoring_refused stage=%s\n' "$1" > /logs/verifier/failure-stage.txt
  printf '0\n' > /logs/verifier/reward.txt
  exit 0
}

# ---------------------------------------------------------------------------
# Hermetic Git provenance.
#
# Only `git diff` (and log/show) consult external diff & textconv drivers, and
# only when gitattributes select them -- so this does NOT claim that rev-parse
# or status "run all hooks". The concrete vectors neutralised here are:
#   * repo/user/system config injecting diff.*.command / *.textconv,
#   * .gitattributes selecting such a driver,
#   * core.fsmonitor running a candidate hook binary,
#   * core.hooksPath / GIT_* environment overrides.
# GIT_CONFIG_GLOBAL/SYSTEM=/dev/null drop user & system config; the explicit -c
# flags override anything the candidate's in-repo config could set.
# ---------------------------------------------------------------------------
git_trusted() {
  env -u GIT_DIR -u GIT_WORK_TREE -u GIT_INDEX_FILE -u GIT_OBJECT_DIRECTORY \
      -u GIT_ALTERNATE_OBJECT_DIRECTORIES -u GIT_CONFIG -u GIT_CONFIG_COUNT \
      -u GIT_EXTERNAL_DIFF -u GIT_ATTR_NOSYSTEM -u GIT_HOOKS_PATH \
      GIT_CONFIG_GLOBAL=/dev/null \
      GIT_CONFIG_SYSTEM=/dev/null \
      GIT_TERMINAL_PROMPT=0 \
      GIT_OPTIONAL_LOCKS=0 \
    git -c "safe.directory=${REPO}" \
        -c core.fsmonitor=false \
        -c core.hooksPath=/dev/null \
        -c core.attributesFile=/dev/null \
        -c diff.external= \
        -c diff.noprefix=false \
        -c core.pager=cat \
        -c protocol.version=2 \
        --no-optional-locks \
        -C "${REPO}" "$@"
}

base_commit="$(git_trusted rev-parse HEAD)" || fail_closed base_commit
# --no-ext-diff and --no-textconv defeat attribute-selected external drivers.
candidate_patch_sha256="$(
  git_trusted diff --binary --no-ext-diff --no-textconv HEAD \
    | sha256sum | awk '{print $1}'
)" || fail_closed candidate_patch
candidate_status="$(git_trusted status --short --no-renames)" \
  || fail_closed candidate_status
{
  printf 'base_commit=%s\n' "${base_commit}"
  printf 'candidate_patch_sha256=%s\n' "${candidate_patch_sha256}"
  printf 'provenance_mode=hermetic_git\n'
  printf '%s\n' "${candidate_status}"
} > /logs/verifier/candidate-provenance.txt

# ---------------------------------------------------------------------------
# Stage trusted components into a root-owned dir and execute the COPIES, never
# the /tests originals.
# ---------------------------------------------------------------------------
STAGING=/trusted/staging          # root-owned staged trusted CODE
ARTIFACT_STAGING=/trusted/artifact  # root-owned frozen native ARTIFACT (wiped by the stager)
WORKER_TMP=/tmp/moe-worker
WORKER_UID=65534
WORKER_GID=65534
rm -rf "${STAGING}"
mkdir -p "${STAGING}" || fail_closed staging_mkdir
for f in verify_moe_permute.py trusted_timing.py trusted_stage_native.py \
         trusted_expected.py trusted_performance.py trusted_python.py; do
  cp "/tests/${f}" "${STAGING}/${f}" || fail_closed "staging_copy_${f}"
done
chown -R 0:0 "${STAGING}" || fail_closed staging_chown
chmod 755 "${STAGING}" || fail_closed staging_chmod
find "${STAGING}" -type f -exec chmod 0444 {} + || fail_closed staging_chmod_files
{
  printf 'staged_verifier_sha256=%s\n' \
    "$(sha256sum "${STAGING}/verify_moe_permute.py" | awk '{print $1}')"
  printf 'staged_timing_sha256=%s\n' \
    "$(sha256sum "${STAGING}/trusted_timing.py" | awk '{print $1}')"
} > /logs/verifier/staging-provenance.txt

# Scratch ROOT for the unprivileged workers: root-owned 0755, holding no state
# this scorer reads. Each worker gets its OWN 0700 directory underneath, owned by
# the worker uid, so one stage cannot read or plant another's cache -- and no
# shared 1777 directory ever carries state the parent depends on.
rm -rf "${WORKER_TMP}"
mkdir -p "${WORKER_TMP}" || fail_closed worker_tmp_mkdir
chown 0:0 "${WORKER_TMP}" || fail_closed worker_tmp_chown
chmod 0755 "${WORKER_TMP}" || fail_closed worker_tmp_chmod

# Create a unique private cache/home for one worker stage. Echoes the path.
new_worker_cache() {
  local stage="$1"
  local d="${WORKER_TMP}/${stage}-$$-${RANDOM}"
  mkdir -p "${d}/triton" "${d}/inductor" "${d}/xdg" || return 1
  chown -R "${WORKER_UID}:${WORKER_GID}" "${d}" || return 1
  chmod -R 0700 "${d}" || return 1
  printf '%s' "${d}"
}

# setpriv prefix for the unprivileged workers.
drop_priv=(setpriv "--reuid=${WORKER_UID}" "--regid=${WORKER_GID}" --init-groups --no-new-privs --)

# ---------------------------------------------------------------------------
# Candidate build as the UNPRIVILEGED agent user. root only orchestrates.
# ---------------------------------------------------------------------------
build_user=agent
id -u "${build_user}" >/dev/null 2>&1 || fail_closed build_user_missing
chown -R "${build_user}" "${REPO}" 2>/dev/null || true
mkdir -p "${REPO}/build"
chown -R "${build_user}" "${REPO}/build" 2>/dev/null || true

set +e
setpriv --reuid="$(id -u ${build_user})" --regid="$(id -g ${build_user})" \
        --clear-groups --no-new-privs \
  env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
         HOME=/tmp TMPDIR=/tmp \
         CUDA_HOME=/usr/local/cuda \
    sh /tests/rebuild_for_verification.sh \
      > /logs/verifier/native-build.stdout.log \
      2> /logs/verifier/native-build.stderr.log
build_status=$?
set -e
printf 'build_exit=%s\n' "${build_status}" > /logs/verifier/build-exit.txt
if [ "${build_status}" -ne 0 ]; then
  printf 'build_failed exit=%s\n' "${build_status}" \
    > /logs/verifier/failure-stage.txt
  printf 'build_failed\n' > /logs/verifier/build-stage.txt
  printf '{"build":%s,"correctness":null,"performance":null}\n' \
    "${build_status}" > /logs/verifier/stages.json
  printf '0\n' > /logs/verifier/reward.txt
  exit 0
fi
printf 'build_passed\n' > /logs/verifier/build-stage.txt

# ---------------------------------------------------------------------------
# root freezes exactly one native artifact into root-owned staging, by directory
# listing + lstat/O_NOFOLLOW/SHA-256 -- never via find_spec.
# ---------------------------------------------------------------------------
rm -f "${STAGE_MANIFEST}"
python3 -I -S "${STAGING}/trusted_python.py" "${STAGING}/trusted_stage_native.py" \
  --staging-dir "${ARTIFACT_STAGING}" --manifest "${STAGE_MANIFEST}" \
  > /logs/verifier/native-staging.log 2>&1
stage_rc=$?
cat /logs/verifier/native-staging.log
[ "${stage_rc}" -eq 0 ] || fail_closed native_staging
[ -s "${STAGE_MANIFEST}" ] || fail_closed native_staging_manifest

staged_path="$(python3 -I -S "${STAGING}/trusted_python.py" -c 'import json,sys;print(json.load(open(sys.argv[1]))["staged_path"])' "${STAGE_MANIFEST}")" \
  || fail_closed staged_path
staged_sha="$(python3 -I -S "${STAGING}/trusted_python.py" -c 'import json,sys;print(json.load(open(sys.argv[1]))["sha256"])' "${STAGE_MANIFEST}")" \
  || fail_closed staged_sha

# ---------------------------------------------------------------------------
# Untrusted workers: they may import the candidate, but can only load the staged
# artifact, and their exit codes alone decide nothing.
# ---------------------------------------------------------------------------
correctness_rc=0
performance_rc=0
# The staged artifact is 0444 root:root, so the unprivileged worker can read but
# not replace it. HOME/TRITON_* are required because uid 65534 has
# HOME=/nonexistent, which would otherwise break Triton/inductor.
# Build a worker env bound to a UNIQUE private 0700 cache for this stage.
make_worker_env() {
  local cache
  cache="$(new_worker_cache "$1")" || fail_closed "worker_cache_${1}"
  worker_env=(env
    MOE_STAGED_NATIVE="${staged_path}"
    MOE_STAGED_SHA256="${staged_sha}"
    MOE_EXPECT_UID="${WORKER_UID}"
    HOME="${cache}"
    TMPDIR="${cache}"
    TRITON_HOME="${cache}"
    TRITON_CACHE_DIR="${cache}/triton"
    TORCHINDUCTOR_CACHE_DIR="${cache}/inductor"
    XDG_CACHE_HOME="${cache}/xdg"
    CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}")
}
make_worker_env correctness

# The unprivileged worker must be able to read the candidate tree.
chmod o+rx /app 2>/dev/null || true

"${drop_priv[@]}" "${worker_env[@]}" \
  python3 -I -S "${STAGING}/trusted_python.py" "${STAGING}/verify_moe_permute.py" --stage correctness \
  > /logs/verifier/correctness.log 2>&1 || correctness_rc=$?
if [ "${correctness_rc}" -eq 0 ]; then
  make_worker_env performance
  "${drop_priv[@]}" "${worker_env[@]}" \
    python3 -I -S "${STAGING}/trusted_python.py" "${STAGING}/verify_moe_permute.py" --stage performance \
    > /logs/verifier/performance.log 2>&1 || performance_rc=$?
else
  performance_rc=125
  printf 'skipped: correctness failed\n' > /logs/verifier/performance.log
fi
cat /logs/verifier/correctness.log
cat /logs/verifier/performance.log

# Real build status recorded (never hardcoded 0).
printf '{"build":%s,"correctness":%s,"performance":%s}\n' \
  "${build_status}" "${correctness_rc}" "${performance_rc}" \
  > /logs/verifier/stages.json

# ---------------------------------------------------------------------------
# Scoring entry: structural manifest check. Required stages are declared HERE.
# ---------------------------------------------------------------------------
python3 -I -S "${STAGING}/trusted_python.py" - \
  "${STAGE_MANIFEST}" "${correctness_rc}" "${performance_rc}" \
  "${build_status}" "${staged_sha}" "${SCORE_MANIFEST}" "${WORKER_UID}" \
  <<'PY' > /logs/verifier/scoring.log 2>&1
import json, math, pathlib, sys

sys.path.insert(0, "/tests")
import trusted_expected  # noqa: E402  task-owned, no candidate imports
from trusted_performance import validate_performance

EXPECTED_CASE_DIGESTS = trusted_expected.expected_digests()
EXPECTED_TIMING_PROTOCOL = trusted_expected.EXPECTED_TIMING_PROTOCOL
EXPECTED_TIME_CASE_CALLS = trusted_expected.EXPECTED_TIME_CASE_CALLS

stage_manifest, c_rc, p_rc, b_rc, staged_sha, out_path, worker_uid = sys.argv[1:8]
REQUIRED_STAGES = ("build", "native_staging", "correctness", "performance")
REQUIRED_MARKERS = {
    "correctness": "MOE_PERMUTE_CORRECTNESS_STAGE=PASS",
    "performance": "MOE_PERMUTE_PERFORMANCE_STAGE=PASS",
}
LOGS = {
    "correctness": "/logs/verifier/correctness.log",
    "performance": "/logs/verifier/performance.log",
}

manifest = {
    "schema": "moe-permute-scoring-manifest/1",
    "verdict": "FAIL",
    "reason": "scoring_did_not_complete",
    "required_stages": list(REQUIRED_STAGES),
    "stages": {},
}
pathlib.Path(out_path).write_text(json.dumps(manifest, indent=2, sort_keys=True))

problems = []
try:
    stg = json.load(open(stage_manifest))
except Exception as exc:
    stg = {}
    problems.append(f"staging_manifest_unreadable:{exc}")

manifest["stages"]["build"] = {"exit_code": int(b_rc), "satisfied": int(b_rc) == 0}
if int(b_rc) != 0:
    problems.append(f"build:exit={b_rc}")

staging_ok = stg.get("staging") == "OK" and stg.get("sha256") == staged_sha
manifest["stages"]["native_staging"] = {
    "staging": stg.get("staging"),
    "sha256": stg.get("sha256"),
    "staged_path": stg.get("staged_path"),
    "satisfied": bool(staging_ok),
}
if not staging_ok:
    problems.append("native_staging:not_ok_or_sha_mismatch")

for stage, rc in (("correctness", c_rc), ("performance", p_rc)):
    rec = {"exit_code": int(rc), "marker_present": False,
           "sha_in_log": False, "satisfied": False}
    try:
        text = pathlib.Path(LOGS[stage]).read_text()
    except Exception:
        text = ""
        problems.append(f"{stage}:log_unreadable")
    rec["marker_present"] = text.splitlines().count(REQUIRED_MARKERS[stage]) == 1
    # The worker must have loaded the SAME artifact root staged.
    rec["sha_in_log"] = staged_sha in text

    # ---- Observation CONTENT, not just structure --------------------------
    # The worker must prove it ran unprivileged, and must report real call
    # counts / output digests. A structurally valid log with fabricated or
    # absent observations is refused.
    payload = None
    payloads = []
    for line in text.splitlines():
        line = line.strip()
        if not (line.startswith("{") and line.endswith("}")):
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict) and "actual_uid" in obj:
            payloads.append(obj)
    if len(payloads) == 1:
        payload = payloads[0]
    rec["payload_count"] = len(payloads)
    rec["payload_found"] = payload is not None
    rec["uid_ok"] = False
    rec["counts_ok"] = False
    rec["digests_ok"] = False
    if payload is not None:
        rec["actual_uid"] = payload.get("actual_uid")
        rec["uid_ok"] = (
            payload.get("actual_uid") == int(worker_uid)
            and payload.get("actual_uid") != 0
        )
        counts = payload.get("call_counts") or {}
        if stage == "correctness":
            want = len(EXPECTED_CASE_DIGESTS)
            rec["counts_ok"] = counts.get("check_case") == want
            digests = payload.get("case_digests") or {}
            # Compare EVERY case against the digest this scorer derived itself
            # from reference semantics. Distinctness is NOT the test: 18 randomly
            # generated distinct digests fail here because none of them equals
            # the independently recomputed expectation.
            mismatched = [
                k for k, want_d in EXPECTED_CASE_DIGESTS.items()
                if digests.get(k) != want_d
            ]
            rec["digest_mismatched_cases"] = mismatched[:5]
            rec["digests_ok"] = (
                sorted(digests) == sorted(EXPECTED_CASE_DIGESTS)
                and not mismatched
            )
        else:
            rec["counts_ok"] = counts.get("time_case") == EXPECTED_TIME_CASE_CALLS
            measurement = validate_performance(payload)
            rec["measurement_validation"] = measurement
            rec["digests_ok"] = measurement["valid"]

    rec["satisfied"] = bool(
        int(rc) == 0 and rec["marker_present"] and rec["sha_in_log"]
        and rec["payload_found"] and rec["uid_ok"]
        and rec["counts_ok"] and rec["digests_ok"]
    )
    if int(rc) != 0:
        problems.append(f"{stage}:exit={rc}")
    if not rec["marker_present"]:
        problems.append(f"{stage}:missing_marker")
    if not rec["sha_in_log"]:
        problems.append(f"{stage}:staged_sha_absent_from_log")
    if not rec["payload_found"]:
        problems.append(f"{stage}:observation_payload_absent")
    if not rec["uid_ok"]:
        problems.append(f"{stage}:worker_uid_not_dropped={rec.get('actual_uid')}")
    if not rec["counts_ok"]:
        problems.append(f"{stage}:call_count_mismatch")
    if not rec["digests_ok"]:
        if stage == "correctness":
            problems.append(
                f"{stage}:case_digest_mismatch_vs_trusted="
                f"{rec.get('digest_mismatched_cases')}"
            )
        else:
            problems.append(
                f"{stage}:measurement_invalid="
                f"{rec.get('measurement_validation')}"
            )
    manifest["stages"][stage] = rec

satisfied = sorted(k for k, v in manifest["stages"].items() if v.get("satisfied"))
if satisfied != sorted(REQUIRED_STAGES):
    problems.append(
        "stage_set_mismatch missing="
        + str(sorted(set(REQUIRED_STAGES) - set(satisfied)))
    )

manifest["satisfied_stages"] = satisfied
manifest["unsatisfied_stages"] = sorted(set(REQUIRED_STAGES) - set(satisfied))
if problems:
    manifest["verdict"] = "FAIL"
    manifest["reason"] = "; ".join(problems)
else:
    manifest["verdict"] = "PASS"
    manifest["reason"] = "all_required_stages_satisfied"
pathlib.Path(out_path).write_text(json.dumps(manifest, indent=2, sort_keys=True))

if problems:
    print("scoring_refused=" + "; ".join(problems))
    sys.exit(1)
print("SCORING_MANIFEST=COMPLETE stages=" + ",".join(sorted(REQUIRED_STAGES)))
sys.exit(0)
PY
scoring_rc=$?
cat /logs/verifier/scoring.log

if [ "${scoring_rc}" -eq 0 ]; then
  printf '1\n' > /logs/verifier/reward.txt
else
  printf 'scoring_manifest_incomplete rc=%s\n' "${scoring_rc}" \
    > /logs/verifier/failure-stage.txt
  printf '0\n' > /logs/verifier/reward.txt
fi
