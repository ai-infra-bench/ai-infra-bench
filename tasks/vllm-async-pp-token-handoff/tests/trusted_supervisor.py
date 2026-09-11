#!/usr/bin/env python3
"""Trusted supervisor for the async-PP token-handoff verifier.

Boundary contract
-----------------
This process is the ONLY component whose output is allowed to influence the
final reward. It runs as root and MUST NOT import the candidate ``vllm``
package, the candidate ``tests.*`` tree, or any module resolved out of
``/workspace/repo``. It therefore never executes candidate code in-process.

Everything the candidate can influence runs in *untrusted worker* children.
A worker's only channel to the supervisor is a single framed payload on stdout:

    ##ASYNC_PP_PAYLOAD <nonce> <one-line-json> ##END

The supervisor independently declares the required stages (REQUIRED_STAGES
below), mints a fresh per-stage nonce, records for every child its launch, its
declared rank, its exit code and its framed payloads, and only then decides.

A stage is satisfied ONLY when every one of these holds:
  * the child was launched by this supervisor,
  * the child exited 0,
  * exactly one well-formed frame arrived per required rank,
  * the frame's nonce equals the nonce minted for this stage (defeats stale or
    pre-planted payloads: the nonce does not exist before launch),
  * the frame's declared rank set equals the required rank set exactly -- no
    missing rank, no duplicate rank, no extra rank,
  * the payload declares ``stage_completed: true`` and carries the required
    per-stage observation keys.

Anything else -- import-time ``sys.exit(0)``, a crash before reporting, a
truncated or malformed frame, a silent rank, a duplicated rank -- leaves a
required stage unsatisfied and the manifest verdict is FAIL. The supervisor
fails closed: the verdict is FAIL unless it is positively established.

What is INDEPENDENTLY established by this process (not self-reported):
  * rank identity -- each rank is spawned as its own child with its own stdout
    pipe, so identity comes from process association. The ``rank`` field inside a
    payload is NEVER used to decide which rank reported;
  * per-rank exit status and per-rank frame count;
  * the worker's effective uid, read from /proc/<pid>/status by this parent
    while the child is alive -- not from any value the worker prints;
  * that a required stage ran at all (a stage that dies before framing is
    unsatisfied).

What is NOT a secret, and therefore NOT a security argument:
  * the per-stage challenge file and this source file are readable by the
    worker. An earlier version of this module claimed a worker "cannot obtain the
    expected digest" -- that claim was WRONG and has been removed. The worker can
    read both. The digest is an INTEGRITY check (it catches a worker reporting
    values that disagree with the task's own expectation), NOT proof of work.

RESIDUAL RISK, explicitly still open (not claimed closed):
  * a worker that executes candidate code can print a well-formed frame whose
    observation values are fabricated but happen to equal the expected ones. The
    fields ``gpu_collective_seen``, ``sender_lifecycle`` and ``call_counts`` are
    worker-declared and cannot be confirmed by this parent; they are recorded as
    observations only. Closing that requires either in-parent recomputation of
    the observed quantity or kernel/collective instrumentation outside the
    worker's reach, neither of which is implemented here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import signal
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
import sys
from pathlib import Path

# Executed copies live in a root-owned staging tree, NOT under /tests. The
# supervisor never executes the /tests copy directly (mirrors the PR4 pattern).
STAGING = os.environ.get("ASYNC_PP_STAGING", "/trusted/staging")
VERIFIER = os.path.join(STAGING, "verify_async_pp.py")

# Unprivileged worker identity. Workers import the candidate `vllm`; running them
# as root would put candidate code in a privileged process, which is exactly the
# boundary this supervisor exists to establish.
WORKER_UID = 65534
WORKER_GID = 65534
# Writable scratch for the unprivileged worker, created 1777 by the scorer.
WORKER_TMP = os.environ.get("ASYNC_PP_WORKER_TMP", "/tmp/async-pp-worker")
# The candidate work tree: the ONLY vLLM the workers are allowed to judge.
CANDIDATE_REPO = os.environ.get("ASYNC_PP_CANDIDATE_REPO", "/workspace/repo")

# ---------------------------------------------------------------------------
# Task-owned expected observations.
#
# Framing + nonce prove a payload is fresh and structurally complete, but NOT
# that its contents describe real work. These are the values a correct
# implementation must report, derived here in the trusted parent from the task's
# own scenario definitions. Inputs and expected digests are readable by workers;
# the supervisor checks consistency, without treating those values as secrets.
# ---------------------------------------------------------------------------
EXPECTED_OBSERVATIONS: dict[str, dict] = {
    "CONFIG": {
        "async_scheduling_allowed": True,
        "pipeline_parallel_size": 2,
    },
    "SCHEDULER_REENTRY": {
        "scheduler_reentry_request_counts": [1, 3],
    },
    "NCCL_BASIC": {
        "scenario": "basic",
        "gpu_collective_seen": True,
        "world_size": 2,
    },
    "NCCL_REORDERED": {
        "scenario": "reordered",
        "gpu_collective_seen": True,
        "world_size": 2,
    },
    "NCCL_INTEGRATED": {
        "scenario": "integrated",
        "gpu_collective_seen": True,
        "world_size": 2,
    },
}

# Per-stage token payload digests a correct run must reproduce. Computed from the
# task-owned scenario token lists. These verify report consistency, not proof
# that a worker executed the collective.
# Duplicated here deliberately: the supervisor must NOT import the verifier,
# because that module imports the candidate `vllm`. Any drift between these and
# tests/verify_async_pp.py SCENARIOS is caught by the digest comparison itself.
SCENARIO_TOKENS: dict[str, list[int]] = {
    "NCCL_BASIC": [101, 202],
    "NCCL_REORDERED": [303, 404, 505],
    "NCCL_INTEGRATED": [606, 707, 808],
}


def expected_stage_digest(stage: str, tokens: list[int]) -> str:
    """Digest over the canonical token payload for a scenario."""
    canonical = json.dumps({"stage": stage, "tokens": list(tokens)},
                           sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def drop_priv_argv() -> list[str]:
    """setpriv prefix that runs a worker as uid/gid 65534 with no new privs."""
    return [
        "setpriv",
        f"--reuid={WORKER_UID}",
        f"--regid={WORKER_GID}",
        "--init-groups",
        "--no-new-privs",
        "--",
    ]
FRAME_RE = re.compile(
    r"^##ASYNC_PP_PAYLOAD\s+(?P<nonce>[0-9a-f]{32})\s+(?P<body>\{.*\})\s+##END$"
)

# The supervisor's own independent declaration of what MUST run. This is not
# derived from the worker's output, from the candidate tree, or from argv.
REQUIRED_STAGES: dict[str, dict] = {
    "CONFIG": {
        "kind": "single",
        "argv": ["--check-config"],
        "ranks": [0],
        "required_keys": ["async_scheduling_allowed", "pipeline_parallel_size"],
        "expected_call_counts": {"config_built": 1},
    },
    "SCHEDULER_REENTRY": {
        "kind": "single",
        "argv": ["--check-scheduler"],
        "ranks": [0],
        "required_keys": ["scheduler_reentry_cases"],
        # Two request-count cases, each scheduled twice (first + re-entry).
        "expected_call_counts": {"schedule_calls": 4},
    },
    "NCCL_BASIC": {
        "kind": "dist",
        "argv": ["--scenario", "basic"],
        "ranks": [0, 1],
        "port": 29618,
        "required_keys": ["scenario", "gpu_collective_seen", "sender_lifecycle"],
        # One production sample_tokens per rank, one GPU broadcast.
        "expected_call_counts": {"execute_model_calls": 1, "sample_tokens_calls": 1},
    },
    "NCCL_REORDERED": {
        "kind": "dist",
        "argv": ["--scenario", "reordered"],
        "ranks": [0, 1],
        "port": 29619,
        "required_keys": ["scenario", "gpu_collective_seen", "sender_lifecycle"],
        # One production sample_tokens per rank, one GPU broadcast.
        "expected_call_counts": {"execute_model_calls": 1, "sample_tokens_calls": 1},
    },
    "NCCL_INTEGRATED": {
        "kind": "dist",
        "argv": ["--scenario", "integrated"],
        "ranks": [0, 1],
        "port": 29620,
        "required_keys": ["scenario", "gpu_collective_seen", "sender_lifecycle"],
        # One production sample_tokens per rank, one GPU broadcast.
        "expected_call_counts": {"execute_model_calls": 1, "sample_tokens_calls": 1},
    },
}

# Ranks that performed the GPU broadcast must prove they finished the whole
# post-broadcast protocol, not merely that the broadcast was observed.
SENDER_LIFECYCLE_STEPS = ("production_returned", "downstream_consumed", "barrier", "final_report")


def parse_frames(text: str) -> tuple[list[dict], list[str]]:
    """Extract framed payloads. Returns (frames, anomalies)."""
    frames: list[dict] = []
    anomalies: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if "##ASYNC_PP_PAYLOAD" not in line:
            continue
        m = FRAME_RE.match(line)
        if not m:
            anomalies.append("malformed_frame")
            continue
        try:
            body = json.loads(m.group("body"))
        except json.JSONDecodeError:
            anomalies.append("undecodable_frame_json")
            continue
        if not isinstance(body, dict):
            anomalies.append("frame_not_object")
            continue
        body["_nonce"] = m.group("nonce")
        frames.append(body)
    return frames, anomalies


# A worker must never be able to hang the scorer. Every wait is bounded, and the
# child's whole process group is reaped even on the error paths.
RANK_TIMEOUT_S = 300


def _reap_group(proc: subprocess.Popen) -> None:
    """Kill the child's entire process group if anything survives."""
    if proc.poll() is None:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(os.getpgid(proc.pid), sig)
            except (ProcessLookupError, PermissionError, OSError):
                break
            try:
                proc.wait(timeout=5)
                return
            except subprocess.TimeoutExpired:
                continue
    # Close the pipe so a surviving grandchild cannot keep this parent blocked.
    if proc.stdout is not None:
        try:
            proc.stdout.close()
        except OSError:
            pass


def _kill_group_and_drain(proc: subprocess.Popen) -> str:
    """Kill the group, then take whatever output is already buffered."""
    _reap_group(proc)
    try:
        out, _ = proc.communicate(timeout=10)
        return out or ""
    except Exception:  # noqa: BLE001 - bounded: never re-block here
        return ""


def _read_uid(pid: int) -> int | None:
    """One /proc sample of a pid's effective uid."""
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("Uid:"):
                # Uid:  real  effective  saved  fs
                return int(line.split()[2])
    except OSError:
        return None
    return None


def _observe_dropped_uid(pid: int, expect: int,
                         timeout_s: float = 10.0) -> int | None:
    """Observe the child's effective uid from /proc, tolerating the exec race.

    ``setpriv`` is itself exec'd as root and only then drops privileges, so an
    immediate single sample can legitimately read 0. Poll until the drop is
    observed, the child exits, or the deadline passes. This never trusts anything
    the worker prints; it is the parent's own observation.

    Returns the last uid actually observed (possibly 0, or None if the child was
    already gone), so a genuinely undropped worker is still reported as such.
    """
    deadline = time.monotonic() + timeout_s
    last = None
    while time.monotonic() < deadline:
        uid = _read_uid(pid)
        if uid is None:
            # Process gone: keep whatever we last saw rather than inventing one.
            return last
        last = uid
        if uid == expect:
            return uid
        time.sleep(0.02)
    return last


def _worker_env(stage: str, nonce: str, rank: int, world: int,
                port: int, cache_dir: Path, expected_path: str) -> dict:
    env = dict(os.environ)
    env["ASYNC_PP_NONCE"] = nonce
    env["ASYNC_PP_STAGE"] = stage
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    # Rank identity is assigned BY THIS PARENT, per child.
    env["RANK"] = str(rank)
    env["LOCAL_RANK"] = str(rank)
    env["WORLD_SIZE"] = str(world)
    env["MASTER_ADDR"] = "127.0.0.1"
    env["MASTER_PORT"] = str(port)
    # Unique, private, 0700 cache/home per worker, outside the candidate tree.
    # Never a shared 1777 directory: this parent reads state influenced by it.
    env["HOME"] = str(cache_dir)
    env["TMPDIR"] = str(cache_dir)
    env["TRITON_HOME"] = str(cache_dir)
    env["TRITON_CACHE_DIR"] = str(cache_dir / "triton")
    env["TORCHINDUCTOR_CACHE_DIR"] = str(cache_dir / "inductor")
    env["XDG_CACHE_HOME"] = str(cache_dir / "xdg")
    env["ASYNC_PP_EXPECT_UID"] = str(WORKER_UID)
    env["ASYNC_PP_CHALLENGE"] = expected_path
    # Authoritative import root: the CANDIDATE work tree. Set explicitly so a
    # worker can never fall back to the pre-installed vLLM in dist-packages.
    env["PYTHONPATH"] = CANDIDATE_REPO
    return env


def _spawn_rank(stage: str, spec: dict, rank: int, nonce: str,
                expected_path: str, log_dir: Path) -> dict:
    """Spawn ONE rank as its own child with its own stdout pipe.

    Rank identity is established by this spawn, not by anything the child says.
    """
    world = len(spec["ranks"])
    cache_dir = Path(WORKER_TMP) / f"{stage}-rank{rank}-{nonce[:8]}"
    for sub in ("", "triton", "inductor", "xdg"):
        (cache_dir / sub if sub else cache_dir).mkdir(parents=True, exist_ok=True)
    # 0700 owned by the worker uid: private to that worker, not world-writable.
    for path in [cache_dir, *cache_dir.iterdir()]:
        os.chown(path, WORKER_UID, WORKER_GID)
        os.chmod(path, 0o700)

    # Isolation flag choice matters here. `-I` implies `-E`, which DISCARDS the
    # image's PYTHONPATH=/workspace/repo and silently redirects `import vllm` to
    # the pre-installed vLLM in dist-packages -- i.e. the worker would judge the
    # WRONG code (for this task, a dist-packages async+PP guard that the
    # candidate base commit does not contain). We therefore use `-s` (ignore user
    # site-packages) without `-E`, and pin PYTHONPATH to the candidate tree in
    # the worker env, so the candidate work tree stays authoritative.
    inner = [sys.executable, "-s", VERIFIER, *spec["argv"]]
    argv = drop_priv_argv() + inner
    rec = {
        "rank_assigned_by_parent": rank,
        "child_launched": False,
        "pid": None,
        "exit_code": None,
        "timed_out": False,
        "effective_uid_observed": None,
        "frames": [],
        "anomalies": [],
    }
    try:
        # start_new_session puts the child in its OWN process group, so a
        # grandchild that outlives it (and would otherwise hold the stdout pipe
        # open forever) can be killed as a group. A worker must never be able to
        # hang the trusted scorer: that would itself be a scoring defect.
        proc = subprocess.Popen(
            argv, cwd="/workspace/repo",
            env=_worker_env(stage, nonce, rank, world, spec.get("port", 0),
                            cache_dir, expected_path),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            start_new_session=True,
        )
    except OSError as exc:
        rec["anomalies"].append(f"spawn_failed:{type(exc).__name__}")
        return rec
    rec["child_launched"] = True
    rec["pid"] = proc.pid
    # The parent's own observation of the privilege drop, polled past the
    # setpriv exec race. Never a value the worker printed.
    rec["effective_uid_observed"] = _observe_dropped_uid(proc.pid, WORKER_UID)

    out = ""
    try:
        out, _ = proc.communicate(timeout=RANK_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        rec["timed_out"] = True
        rec["anomalies"].append("rank_timeout")
        out = _kill_group_and_drain(proc)
    except Exception as exc:  # noqa: BLE001 - fail closed, never hang
        rec["anomalies"].append(f"communicate_failed:{type(exc).__name__}")
        out = _kill_group_and_drain(proc)
    finally:
        # Guarantee no stray group survives to hold the pipe or the GPU.
        _reap_group(proc)
    rec["exit_code"] = proc.returncode
    (log_dir / f"stage-{stage}-rank{rank}.log").write_text(out or "")

    frames, anomalies = parse_frames(out or "")
    rec["anomalies"].extend(anomalies)
    for f in frames:
        if f.get("_nonce") != nonce:
            rec["anomalies"].append("nonce_mismatch")
            continue
        # A frame claiming a DIFFERENT rank than the one this pipe belongs to is
        # a forgery attempt by the surviving rank. Rejected on identity grounds:
        # the payload's self-reported rank is never authoritative.
        claimed = f.get("rank")
        if claimed is not None and claimed != rank:
            rec["anomalies"].append(
                f"rank_forgery:pipe_rank={rank}_claimed={claimed}"
            )
            continue
        rec["frames"].append(f)
    if len(rec["frames"]) != 1:
        rec["anomalies"].append(f"frames_on_this_pipe={len(rec['frames'])}!=1")
    return rec


def run_stage(stage: str, spec: dict, log_dir: Path) -> dict:
    """Run one required stage: one child per required rank, each with its own pipe."""
    nonce = secrets.token_hex(16)

    # The challenge file is NOT a secret -- the worker can read it. It exists so a
    # stage's expectation is pinned per run, not to hide the answer.
    expected_digest = None
    if stage in SCENARIO_TOKENS:
        expected_digest = expected_stage_digest(stage, SCENARIO_TOKENS[stage])
    expected_path = str(log_dir / f"challenge-{stage}.json")
    Path(expected_path).write_text(json.dumps(
        {"stage": stage, "nonce": nonce,
         "expected_payload_digest": expected_digest}, sort_keys=True))
    os.chmod(expected_path, 0o444)

    record: dict = {
        "stage": stage,
        "required_ranks": list(spec["ranks"]),
        "nonce_minted": True,
        "expected_observations": EXPECTED_OBSERVATIONS.get(stage, {}),
        "expected_payload_digest": expected_digest,
        "ranks": {},
        "anomalies": [],
        "satisfied": False,
    }

    # One child per rank, sequentially for single-rank stages and concurrently for
    # distributed ones (they must rendezvous with each other).
    if len(spec["ranks"]) == 1:
        results = {spec["ranks"][0]:
                   _spawn_rank(stage, spec, spec["ranks"][0], nonce,
                               expected_path, log_dir)}
    else:
        # Each _spawn_rank is already individually bounded by RANK_TIMEOUT_S; the
        # outer wait adds a margin so a wedged thread cannot stall the stage
        # forever. A rank whose result never arrives is recorded as unlaunched,
        # which leaves the stage unsatisfied (fail closed).
        pool = ThreadPoolExecutor(max_workers=len(spec["ranks"]))
        try:
            futures = {
                rank: pool.submit(_spawn_rank, stage, spec, rank, nonce,
                                  expected_path, log_dir)
                for rank in spec["ranks"]
            }
            results = {}
            for rank, fut in futures.items():
                try:
                    results[rank] = fut.result(timeout=RANK_TIMEOUT_S + 60)
                except FuturesTimeout:
                    results[rank] = {
                        "rank_assigned_by_parent": rank,
                        "child_launched": False, "pid": None,
                        "exit_code": None, "timed_out": True,
                        "effective_uid_observed": None, "frames": [],
                        "anomalies": ["supervisor_wait_timeout"],
                    }
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    record["ranks"] = {str(k): v for k, v in results.items()}

    # ---- Parent-side, independently established facts -----------------------
    launched = [r for r in results.values() if r["child_launched"]]
    if len(launched) != len(spec["ranks"]):
        record["anomalies"].append("not_all_ranks_launched")
    for rank, rec in results.items():
        if rec["exit_code"] != 0:
            record["anomalies"].append(f"rank{rank}_exit={rec['exit_code']}")
        if rec["timed_out"]:
            record["anomalies"].append(f"rank{rank}_timeout")
        # The parent's own /proc reading, not the worker's claim.
        if rec["effective_uid_observed"] not in (WORKER_UID,):
            record["anomalies"].append(
                f"rank{rank}_uid_observed={rec['effective_uid_observed']}"
            )
        for a in rec["anomalies"]:
            record["anomalies"].append(f"rank{rank}:{a}")

    # Exactly one frame per required rank, attributed by pipe not by payload.
    reported = sorted(int(r) for r, rec in record["ranks"].items()
                      if len(rec["frames"]) == 1)
    record["ranks_reported"] = reported
    record["missing_ranks"] = sorted(set(spec["ranks"]) - set(reported))
    record["duplicate_ranks"] = sorted(
        int(r) for r, rec in record["ranks"].items() if len(rec["frames"]) > 1
    )
    # With per-rank pipes an "unexpected rank" cannot arise by construction: a
    # frame claiming another rank is rejected as rank_forgery on its own pipe.
    # Recorded explicitly so the invariant is visible in the manifest.
    record["unexpected_ranks"] = sorted(
        set(reported) - set(spec["ranks"])
    )
    record["frames_seen"] = sum(len(rec["frames"]) for rec in results.values())

    # ---- Observation content (worker-declared; integrity-checked) ------------
    for rank, rec in results.items():
        for f in rec["frames"]:
            if f.get("stage") != stage:
                record["anomalies"].append("frame_stage_mismatch")
            if f.get("stage_completed") is not True:
                record["anomalies"].append("stage_not_completed")
            # Worker-printed uid must agree with the parent's /proc observation.
            if f.get("actual_uid") != rec["effective_uid_observed"]:
                record["anomalies"].append(
                    f"rank{rank}:uid_claim_disagrees_with_proc"
                )
            for key in spec["required_keys"]:
                if key not in f:
                    record["anomalies"].append(f"missing_key:{key}")
            for key, want in record["expected_observations"].items():
                if key not in f:
                    record["anomalies"].append(f"missing_observation:{key}")
                elif f[key] != want:
                    record["anomalies"].append(
                        f"observation_mismatch:{key}={f[key]!r}!={want!r}"
                    )
            if expected_digest is not None and \
                    f.get("payload_digest") != expected_digest:
                record["anomalies"].append(
                    f"payload_digest_mismatch:{f.get('payload_digest')}"
                )
            life = f.get("sender_lifecycle")
            if life is not None and (
                not isinstance(life, dict)
                or not all(life.get(k) is True for k in SENDER_LIFECYCLE_STEPS)
            ):
                record["anomalies"].append("sender_lifecycle_incomplete")
            counts = f.get("call_counts")
            if not isinstance(counts, dict):
                record["anomalies"].append("call_counts_missing")
            else:
                for name, n in spec.get("expected_call_counts", {}).items():
                    if counts.get(name) != n:
                        record["anomalies"].append(
                            f"call_count_mismatch:{name}={counts.get(name)}!={n}"
                        )

    record["satisfied"] = bool(
        not record["anomalies"]
        and not record["missing_ranks"]
        and not record["duplicate_ranks"]
        and record["ranks_reported"] == sorted(spec["ranks"])
        and record["frames_seen"] == len(spec["ranks"])
        and bool(record["expected_observations"])
    )
    return record


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log-dir", default="/logs/verifier")
    ap.add_argument("--manifest", default="/logs/verifier/supervisor-manifest.json")
    args = ap.parse_args()

    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Fail closed: an unwritten/never-finished supervisor must never look like a pass.
    manifest = {
        "schema": "async-pp-supervisor-manifest/1",
        "verdict": "FAIL",
        "reason": "supervisor_did_not_complete",
        "required_stages": sorted(REQUIRED_STAGES),
        "stages": {},
    }
    Path(args.manifest).write_text(json.dumps(manifest, indent=2, sort_keys=True))

    for stage, spec in REQUIRED_STAGES.items():
        manifest["stages"][stage] = run_stage(stage, spec, log_dir)

    satisfied = sorted(s for s, r in manifest["stages"].items() if r["satisfied"])
    # Exact-set comparison: neither a missing stage nor an extra stage passes.
    if satisfied == sorted(REQUIRED_STAGES):
        manifest["verdict"] = "PASS"
        manifest["reason"] = "all_required_stages_satisfied"
    else:
        manifest["verdict"] = "FAIL"
        manifest["reason"] = "required_stage_set_not_satisfied"
    manifest["satisfied_stages"] = satisfied
    manifest["unsatisfied_stages"] = sorted(
        set(REQUIRED_STAGES) - set(satisfied)
    )

    Path(args.manifest).write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"SUPERVISOR_VERDICT={manifest['verdict']}")
    print(f"SUPERVISOR_UNSATISFIED={','.join(manifest['unsatisfied_stages']) or 'none'}")
    return 0 if manifest["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
