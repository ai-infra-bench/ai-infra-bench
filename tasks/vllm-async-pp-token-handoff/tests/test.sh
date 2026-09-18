#!/usr/bin/env bash
# Trusted scoring entry for vllm-async-pp-token-handoff.
#
# Boundary contract:
#   * reward defaults to 0 and is raised ONLY by a positively verified,
#     structurally complete supervisor manifest. Any early return, crash,
#     signal or unreadable manifest therefore scores 0 (fail closed).
#   * This script never imports or executes candidate Python itself, and it
#     never decides anything from a child's exit code alone.
#   * All candidate execution happens inside untrusted workers launched by
#     /tests/trusted_supervisor.py. Scoring requires complete driver reports
#     plus independent GPU input comparison and model output verification.
#   * The trusted preflight below runs BEFORE any candidate import and is where
#     task-owned facts are frozen (see PREFLIGHT FACTS).
set -uo pipefail

mkdir -p /logs/verifier
rm -f /logs/verifier/failure-stage.txt

# Fail closed from the very first line.
printf '0\n' > /logs/verifier/reward.txt

MANIFEST=/logs/verifier/supervisor-manifest.json

fail_closed() {
  printf 'scoring_refused stage=%s\n' "$1" > /logs/verifier/failure-stage.txt
  printf '0\n' > /logs/verifier/reward.txt
  exit 0
}

# ---------------------------------------------------------------------------
# PREFLIGHT FACTS (trusted: established before any candidate code is imported)
#
# Frozen here, by root, from the task-owned /tests tree only:
#   * the opt-125m config fixture content and its SHA-256;
#   * the SHA-256 of the supervisor and of the task-owned fixture module, so a
#     later comparison can detect substitution of the trusted components.
# Facts that CANNOT be established here, and are produced only by the trusted
# supervisor (never by a candidate-containing process):
#   * which required stages ran, their per-rank completion and their nonces;
#   * the final verdict.
# ---------------------------------------------------------------------------
: > /logs/verifier/preflight.log
{
  printf 'supervisor_sha256=%s\n' \
    "$(sha256sum /tests/trusted_supervisor.py | awk '{print $1}')"
  printf 'task_fixtures_sha256=%s\n' \
    "$(sha256sum /tests/task_fixtures.py | awk '{print $1}')"
  printf 'opt125m_config_sha256=%s\n' \
    "$(sha256sum /tests/fixtures/opt-125m/config.json | awk '{print $1}')"
} >> /logs/verifier/preflight.log 2>&1 || fail_closed preflight_hash

# Fixture sanity via stdlib json only -- no transformers, no candidate imports.
python3 -I - <<'PY' >> /logs/verifier/preflight.log 2>&1
import json, sys
cfg = json.load(open("/tests/fixtures/opt-125m/config.json"))
assert cfg["model_type"] == "opt", cfg.get("model_type")
assert cfg["hidden_size"] == 768, cfg.get("hidden_size")
assert cfg["num_hidden_layers"] == 12, cfg.get("num_hidden_layers")
print("LOCAL_OPT_CONFIG=PASS")
PY
if [ $? -ne 0 ]; then
  cat /logs/verifier/preflight.log >&2
  fail_closed preflight_fixture
fi
cat /logs/verifier/preflight.log

# ---------------------------------------------------------------------------
# Stage the trusted components into a root-owned directory and execute the COPIES
# there. /tests may be bind-mounted or otherwise reachable; executing a staged,
# root-owned 0555 copy removes any dependence on /tests staying pristine for the
# duration of the run.
# ---------------------------------------------------------------------------
STAGING=/trusted/staging
WORKER_TMP=/tmp/async-pp-worker
rm -rf "${STAGING}"
mkdir -p "${STAGING}" || fail_closed staging_mkdir
for f in trusted_supervisor.py verify_async_pp.py task_fixtures.py worker_fixtures.py handoff_observer.py lifecycle_cases.py trusted_transport.py mp_e2e.py mp_behavior.py; do
  cp "/tests/${f}" "${STAGING}/${f}" || fail_closed "staging_copy_${f}"
done
cp -r /tests/fixtures "${STAGING}/fixtures" || fail_closed staging_copy_fixtures
chown -R 0:0 "${STAGING}" || fail_closed staging_chown
chmod 755 "${STAGING}" || fail_closed staging_chmod
find "${STAGING}" -type f -exec chmod 0444 {} + || fail_closed staging_chmod_files
chmod 0555 "${STAGING}/trusted_supervisor.py" "${STAGING}/verify_async_pp.py" \
  || fail_closed staging_chmod_exec
{
  printf 'staged_supervisor_sha256=%s\n' \
    "$(sha256sum "${STAGING}/trusted_supervisor.py" | awk '{print $1}')"
  printf 'staged_verifier_sha256=%s\n' \
    "$(sha256sum "${STAGING}/verify_async_pp.py" | awk '{print $1}')"
  printf 'staged_fixtures_sha256=%s\n' \
    "$(sha256sum "${STAGING}/task_fixtures.py" | awk '{print $1}')"
} >> /logs/verifier/preflight.log

# Scratch ROOT for the unprivileged (uid 65534) workers. HOME=/nonexistent would
# otherwise break Triton/inductor for reasons unrelated to the candidate.
#
# This directory is 0755 root-owned and holds NO state this scorer reads. The
# supervisor creates a UNIQUE 0700 directory per worker underneath it, owned by
# the worker uid, so one worker cannot read or plant another's cache -- and no
# shared 1777 directory ever carries state the parent depends on.
rm -rf "${WORKER_TMP}"
mkdir -p "${WORKER_TMP}" || fail_closed worker_tmp_mkdir
chown 0:0 "${WORKER_TMP}" || fail_closed worker_tmp_chown
chmod 0755 "${WORKER_TMP}" || fail_closed worker_tmp_chmod

# The unprivileged worker must be able to read the candidate work tree.
chmod o+rx /workspace /workspace/repo 2>/dev/null || true

# ---------------------------------------------------------------------------
# Untrusted execution, supervised. The supervisor's exit code is recorded but is
# NOT what scoring trusts -- the manifest below is.
# ---------------------------------------------------------------------------
rm -f "${MANIFEST}"
supervisor_rc=0
ASYNC_PP_STAGING="${STAGING}" ASYNC_PP_WORKER_TMP="${WORKER_TMP}" \
python3 -I "${STAGING}/trusted_supervisor.py" \
  --log-dir /logs/verifier --manifest "${MANIFEST}" \
  > /logs/verifier/supervisor.log 2>&1 || supervisor_rc=$?
cat /logs/verifier/supervisor.log
printf 'supervisor_exit=%s\n' "${supervisor_rc}" \
  > /logs/verifier/supervisor-exit.txt

[ -s "${MANIFEST}" ] || fail_closed manifest_missing

# ---------------------------------------------------------------------------
# Scoring entry: read the manifest structurally. The required-stage set is
# re-declared HERE, independently of the manifest, so a manifest that drops a
# stage, adds a stage, or renames one cannot satisfy scoring.
# ---------------------------------------------------------------------------
python3 -I - "${MANIFEST}" <<'PY' > /logs/verifier/scoring.log 2>&1
import json, sys

REQUIRED_STAGES = {"CPU_SUITE": [0], "GPU_SUITE": [0]}
LIFECYCLE = ("production_returned", "downstream_consumed", "barrier", "final_report")
# The unprivileged worker uid this scorer requires the parent to have observed.
EXPECT_WORKER_UID = 65534

try:
    m = json.load(open(sys.argv[1]))
except Exception as exc:
    print(f"scoring_refused=manifest_unreadable {exc}")
    sys.exit(1)

problems = []
if m.get("schema") != "async-pp-supervisor-manifest/1":
    problems.append("schema_mismatch")
if m.get("verdict") != "PASS":
    problems.append(f"verdict={m.get('verdict')}")

stages = m.get("stages")
if not isinstance(stages, dict):
    problems.append("stages_not_object")
    stages = {}

# Exact set equality: no missing stage, no extra stage.
if set(stages) != set(REQUIRED_STAGES):
    problems.append(
        f"stage_set_mismatch missing={sorted(set(REQUIRED_STAGES)-set(stages))} "
        f"extra={sorted(set(stages)-set(REQUIRED_STAGES))}"
    )

for name, ranks in REQUIRED_STAGES.items():
    st = stages.get(name)
    if not isinstance(st, dict):
        problems.append(f"{name}:absent")
        continue
    if name == "GPU_SUITE" and st.get("external_gpu_inputs") is not True:
        problems.append("external_gpu_inputs_missing_or_failed")
    if st.get("satisfied") is not True:
        problems.append(f"{name}:not_satisfied")
    if st.get("anomalies"):
        problems.append(f"{name}:anomalies={st['anomalies'][:4]}")

    # These are driver identities, not PP worker ranks. Each driver has its
    # own parent-observed pipe and uid; the GPU driver owns a real mp executor.
    per_rank = st.get("ranks")
    if not isinstance(per_rank, dict):
        problems.append(f"{name}:no_per_rank_records")
        per_rank = {}
    if sorted(int(k) for k in per_rank) != sorted(ranks):
        problems.append(
            f"{name}:rank_records={sorted(per_rank)}!={sorted(ranks)}"
        )
    for rank in ranks:
        rec = per_rank.get(str(rank))
        if not isinstance(rec, dict):
            problems.append(f"{name}:rank{rank}_missing_record")
            continue
        if rec.get("rank_assigned_by_parent") != rank:
            problems.append(f"{name}:rank{rank}_identity_not_parent_assigned")
        if rec.get("child_launched") is not True:
            problems.append(f"{name}:rank{rank}_not_launched")
        if rec.get("exit_code") != 0:
            problems.append(f"{name}:rank{rank}_exit={rec.get('exit_code')}")
        if rec.get("timed_out"):
            problems.append(f"{name}:rank{rank}_timeout")
        # Parent-observed effective uid (from /proc), not a worker claim.
        if rec.get("effective_uid_observed") != EXPECT_WORKER_UID:
            problems.append(
                f"{name}:rank{rank}_uid_observed="
                f"{rec.get('effective_uid_observed')}"
            )
        # Exactly one frame on this rank's own pipe.
        if len(rec.get("frames") or []) != 1:
            problems.append(
                f"{name}:rank{rank}_frames={len(rec.get('frames') or [])}!=1"
            )
        for a in (rec.get("anomalies") or []):
            if "rank_forgery" in str(a):
                problems.append(f"{name}:rank{rank}_rank_forgery")

    if st.get("ranks_reported") != sorted(ranks):
        problems.append(
            f"{name}:ranks_reported={st.get('ranks_reported')}!={sorted(ranks)}"
        )
    if st.get("missing_ranks"):
        problems.append(f"{name}:missing_ranks={st['missing_ranks']}")
    if st.get("duplicate_ranks"):
        problems.append(f"{name}:duplicate_ranks={st['duplicate_ranks']}")
    if st.get("frames_seen") != len(ranks):
        problems.append(f"{name}:frames_seen={st.get('frames_seen')}!={len(ranks)}")
    if not isinstance(st.get("expected_observations"), dict) or \
            not st["expected_observations"]:
        problems.append(f"{name}:no_expected_observations_declared")
    for token in ("observation_mismatch", "missing_observation",
                  "payload_digest_mismatch", "uid_claim_disagrees_with_proc",
                  "call_count_mismatch", "call_counts_missing",
                  "sender_lifecycle_incomplete"):
        if any(token in str(a) for a in (st.get("anomalies") or [])):
            problems.append(f"{name}:{token}")
    if name in ("NCCL_BASIC", "NCCL_REORDERED", "NCCL_INTEGRATED"):
        if not st.get("expected_payload_digest"):
            problems.append(f"{name}:no_expected_payload_digest")

if problems:
    print("scoring_refused=" + "; ".join(problems))
    sys.exit(1)
print("SCORING_MANIFEST=COMPLETE stages=" + ",".join(sorted(REQUIRED_STAGES)))
sys.exit(0)
PY
scoring_rc=$?
cat /logs/verifier/scoring.log

python3 -I - "${MANIFEST}" <<'PY' > /logs/verifier/stages.json 2>/dev/null || true
import json, sys
try:
    m = json.load(open(sys.argv[1]))
    out = {k: bool(v.get("satisfied")) for k, v in (m.get("stages") or {}).items()}
except Exception:
    out = {}
print(json.dumps(out, sort_keys=True))
PY

# Failed behavior does not need another expensive engine startup. The GPU suite
# already includes the independent observer; candidate reports cannot replace it.
[ "${scoring_rc}" -eq 0 ] || fail_closed behavior_suite

e2e_rc=0
python3 -I "${STAGING}/mp_e2e.py" --log-dir /logs/verifier \
  > /logs/verifier/mp-e2e.log 2>&1 || e2e_rc=$?
[ "${e2e_rc}" -eq 0 ] || fail_closed mp_e2e
printf '1\n' > /logs/verifier/reward.txt
