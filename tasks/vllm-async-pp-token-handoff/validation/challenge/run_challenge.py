#!/usr/bin/env python3
"""External wrapper for the async-PP curator challenge.

The challenge script itself imports the candidate ``vllm`` and therefore cannot
be trusted to report on its own completeness: a bare ``sys.exit(0)`` at import
time exits 0 while running none of the invariants.

This wrapper never imports the candidate. It independently declares the required
scenarios, mints a per-invocation nonce, launches each scenario as a child, and
requires exactly one framed nonce-bearing payload per required rank before it
will report PASS. It fails closed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

CHALLENGE = str(Path(__file__).resolve().parent / "challenge_token_handoff.py")
FRAME_RE = re.compile(
    r"^##CHALLENGE_PAYLOAD\s+(?P<nonce>[0-9a-f]{32})\s+(?P<body>\{.*\})\s+##END$"
)

# Independent declaration -- not read from the challenge, the candidate or argv.
REQUIRED_SCENARIOS: dict[str, dict] = {
    "fresh-interleaved-discard-5req": {
        "ranks": [0, 1],
        "port": 29711,
        "required_keys": ["scenario_result", "gpu_collective_seen"],
    },
    "fresh-interleaved-discard-7req": {
        "ranks": [0, 1],
        "port": 29712,
        "required_keys": ["scenario_result", "gpu_collective_seen"],
    },
}


def run_scenario(name: str, spec: dict, log_dir: Path) -> dict:
    nonce = secrets.token_hex(16)
    env = dict(os.environ)
    env["CHALLENGE_NONCE"] = nonce
    env["CHALLENGE_SCENARIO"] = name
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    cache = log_dir / "worker-cache"
    cache.mkdir(exist_ok=True)
    os.chown(cache, 65534, 65534)
    os.chmod(cache, 0o700)
    env.update(HOME=str(cache), XDG_CACHE_HOME=str(cache / "xdg"),
               TRITON_CACHE_DIR=str(cache / "triton"), TMPDIR=str(cache))
    argv = [
        "setpriv", "--reuid=65534", "--regid=65534", "--clear-groups",
        "--no-new-privs", "--", sys.executable, "-m", "torch.distributed.run",
        "--nnodes=1", f"--nproc-per-node={len(spec['ranks'])}",
        "--master-addr=127.0.0.1", f"--master-port={spec['port']}",
        CHALLENGE,
    ]
    rec: dict = {
        "scenario": name, "child_launched": False, "exit_code": None,
        "timed_out": False, "frames_seen": 0, "ranks_reported": [],
        "missing_ranks": list(spec["ranks"]), "duplicate_ranks": [],
        "unexpected_ranks": [], "anomalies": [], "satisfied": False,
    }
    try:
        proc = subprocess.run(
            argv, cwd="/workspace/repo", env=env, timeout=300,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        rec["child_launched"] = True
        rec["exit_code"] = proc.returncode
        out = proc.stdout or ""
    except subprocess.TimeoutExpired as exc:
        rec["child_launched"] = True
        rec["timed_out"] = True
        rec["anomalies"].append("timeout")
        out = exc.stdout if isinstance(exc.stdout, str) else ""
    except OSError as exc:
        rec["anomalies"].append(f"spawn_failed:{type(exc).__name__}")
        out = ""
    (log_dir / f"challenge-{name}.log").write_text(out)

    seen: dict[int, int] = {}
    for line in out.splitlines():
        line = line.strip()
        if "##CHALLENGE_PAYLOAD" not in line:
            continue
        m = FRAME_RE.match(line)
        if not m:
            rec["anomalies"].append("malformed_frame")
            continue
        if m.group("nonce") != nonce:
            rec["anomalies"].append("nonce_mismatch")
            continue
        try:
            body = json.loads(m.group("body"))
        except json.JSONDecodeError:
            rec["anomalies"].append("undecodable_frame_json")
            continue
        rec["frames_seen"] += 1
        if body.get("scenario_completed") is not True:
            rec["anomalies"].append("scenario_not_completed")
        if body.get("scenario") != name:
            rec["anomalies"].append("scenario_mismatch")
        if body.get("world_size") != len(spec["ranks"]):
            rec["anomalies"].append("world_size_mismatch")
        if body.get("gpu_collective_seen") is not True:
            rec["anomalies"].append("gpu_collective_not_observed")
        if not isinstance(body.get("scenario_result"), dict) or not body["scenario_result"]:
            rec["anomalies"].append("scenario_observations_missing")
        for k in spec["required_keys"]:
            if k not in body:
                rec["anomalies"].append(f"missing_key:{k}")
        r = body.get("rank")
        if isinstance(r, int):
            seen[r] = seen.get(r, 0) + 1
        else:
            rec["anomalies"].append("frame_missing_rank")

    required = set(spec["ranks"])
    rec["ranks_reported"] = sorted(seen)
    rec["duplicate_ranks"] = sorted(r for r, n in seen.items() if n > 1)
    rec["unexpected_ranks"] = sorted(set(seen) - required)
    rec["missing_ranks"] = sorted(required - set(seen))
    rec["satisfied"] = bool(
        rec["child_launched"] and rec["exit_code"] == 0 and not rec["timed_out"]
        and not rec["anomalies"] and not rec["duplicate_ranks"]
        and not rec["unexpected_ranks"] and not rec["missing_ranks"]
        and rec["frames_seen"] == len(required)
    )
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log-dir", default="/logs/challenge")
    ap.add_argument("--manifest", default="/logs/challenge/challenge-manifest.json")
    args = ap.parse_args()
    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema": "async-pp-challenge-manifest/1",
        "verdict": "FAIL",
        "reason": "wrapper_did_not_complete",
        "required_scenarios": sorted(REQUIRED_SCENARIOS),
        "scenarios": {},
    }
    Path(args.manifest).write_text(json.dumps(manifest, indent=2, sort_keys=True))

    for name, spec in REQUIRED_SCENARIOS.items():
        manifest["scenarios"][name] = run_scenario(name, spec, log_dir)

    ok = sorted(n for n, r in manifest["scenarios"].items() if r["satisfied"])
    manifest["satisfied_scenarios"] = ok
    manifest["unsatisfied_scenarios"] = sorted(set(REQUIRED_SCENARIOS) - set(ok))
    if ok == sorted(REQUIRED_SCENARIOS):
        manifest["verdict"] = "PASS"
        manifest["reason"] = "all_required_scenarios_satisfied"
    else:
        manifest["reason"] = "required_scenario_set_not_satisfied"
    Path(args.manifest).write_text(json.dumps(manifest, indent=2, sort_keys=True))

    print(f"CHALLENGE_WRAPPER_VERDICT={manifest['verdict']}")
    print(
        "CHALLENGE_WRAPPER_UNSATISFIED="
        + (",".join(manifest["unsatisfied_scenarios"]) or "none")
    )
    return 0 if manifest["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
