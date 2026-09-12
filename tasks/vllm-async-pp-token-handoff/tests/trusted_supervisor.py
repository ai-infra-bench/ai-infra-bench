#!/usr/bin/env python3
"""Root-owned supervisor; candidate imports occur only in unprivileged children.

The CPU suite and GPU suite each have one driver process. GPU driver rank 0 is
an identity assigned by this parent, not a PP rank. The GPU driver starts a real
mp executor with two Worker processes; both load the candidate implementation.

Per-driver process association, observed uid, exit status, nonce and complete
framing reject missing checks and premature successful exits. Framed values
remain claims made by candidate-containing processes, not independent proof.
For the GPU suite an additional root-owned process supplies fresh samples and
compares actual next-model GPU inputs over separate observation groups.

The supervisor never imports candidate code. Its source and framing protocol
are readable by children; neither is a secret. Python instrumentation inside
candidate-containing workers is not a general security boundary. The controls
establish resistance to the demonstrated report-only and early-exit bypasses,
not arbitrary malicious rewriting of task instrumentation.
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

# Compatible scenarios share a real mp engine and CUDA/NCCL setup. Requests
# are completed or aborted between cases. Each suite must finish before framing.
REQUIRED_STAGES = {
    "CPU_SUITE": {"kind": "single", "argv": ["--suite", "cpu"], "ranks": [0],
                  "required_keys": ["async_scheduling_allowed", "scheduler_reentry_request_counts"],
                  "expected_call_counts": {}},
    "GPU_SUITE": {"kind": "single", "argv": ["--suite", "gpu"], "ranks": [0],
                  "port": 29618, "required_keys": ["scenarios_passed", "sender_lifecycle"],
                  "expected_call_counts": {}},
}
EXPECTED_OBSERVATIONS = {
    "CPU_SUITE": {"async_scheduling_allowed": True, "pipeline_parallel_size": 2,
                  "scheduler_reentry_request_counts": [1, 3]},
    "GPU_SUITE": {"world_size": 2, "scenarios_passed": ["basic", "reordered", "integrated",
                  "compaction", "prefill_progress", "idle", "synchronous"]},
}
SCENARIO_TOKENS = {}

# Legacy frame labels describe driver completion claims. They do not establish
# the PP protocol; independent GPU observations are additionally required.
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
RANK_TIMEOUT_S = 720


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
    began = time.monotonic()
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
    rec["elapsed_seconds"] = round(time.monotonic() - began, 3)
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

    peer_proc = None
    peer_log = None
    peer_result = log_dir / 'trusted-peer-inputs.json'
    if stage == 'GPU_SUITE':
        peer_result.unlink(missing_ok=True)
        peer_log = (log_dir / 'trusted-peer-observer.log').open('w')
        peer_env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME')}
        peer_proc = subprocess.Popen([sys.executable, '-I', str(Path(VERIFIER).parent / 'trusted_transport.py'),
            '--role', 'peer', '--result', str(peer_result)], cwd=str(Path(VERIFIER).parent),
            env=peer_env, stdout=peer_log, stderr=subprocess.STDOUT, start_new_session=True)

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

    if peer_proc is not None:
        try:
            if any(r.get("exit_code") != 0 for r in results.values()):
                raise RuntimeError("candidate suite did not finish")
            peer_proc.wait(timeout=30)
            evidence = json.loads(peer_result.read_text()) if peer_result.exists() else {}
            record['external_gpu_inputs'] = peer_proc.returncode == 0 and evidence.get('passed') is True
        except Exception as exc:
            record['external_gpu_inputs'] = False
            record['anomalies'].append('external_gpu_observer:' + repr(exc))
        finally:
            _reap_group(peer_proc)
            peer_log.close()
        if not record['external_gpu_inputs']:
            record['anomalies'].append('external_gpu_inputs_failed')

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
