#!/usr/bin/env python3
"""External wrapper for the moe_permute curator challenge.

The challenge imports the candidate `vllm` and loads a native artifact, so it
cannot be trusted to report on its own completeness: an import-time
``sys.exit(0)`` would exit 0 having measured nothing.

This wrapper never imports candidate code. It requires the root-staged artifact
path/digest to be supplied, launches the challenge as a child, and demands the
completeness evidence (required scenarios, call counts, staged SHA) before
reporting PASS. It fails closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
from pathlib import Path

CHALLENGE = str(Path(__file__).resolve().parent / "challenge_moe_permute.py")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--staging-manifest",
                    default="/logs/verifier/native-staging.json",
                    help="root-written staging manifest; the authoritative "
                         "source of the staged path and digest")
    ap.add_argument("--staged-native", default=os.environ.get("MOE_STAGED_NATIVE"))
    ap.add_argument("--staged-sha256", default=os.environ.get("MOE_STAGED_SHA256"))
    ap.add_argument("--worker-uid", type=int, default=65534)
    ap.add_argument("--log-dir", default="/logs/challenge")
    ap.add_argument("--manifest", default="/logs/challenge/challenge-manifest.json")
    args = ap.parse_args()

    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema": "moe-permute-challenge-manifest/1",
        "verdict": "FAIL",
        "reason": "wrapper_did_not_complete",
        "child_launched": False,
        "exit_code": None,
        "anomalies": [],
    }
    Path(args.manifest).write_text(json.dumps(manifest, indent=2, sort_keys=True))

    # Resolve the staged artifact from the root staging manifest when it was not
    # passed explicitly. This is the real wiring: the wrapper no longer relies on
    # environment variables that no caller sets.
    if not (args.staged_native and args.staged_sha256):
        try:
            stg = json.load(open(args.staging_manifest))
            if stg.get("staging") == "OK":
                args.staged_native = args.staged_native or stg.get("staged_path")
                args.staged_sha256 = args.staged_sha256 or stg.get("sha256")
                manifest["staging_manifest_used"] = args.staging_manifest
            else:
                manifest["anomalies"].append("staging_manifest_not_ok")
        except Exception as exc:
            manifest["anomalies"].append(
                f"staging_manifest_unreadable:{type(exc).__name__}"
            )

    if not args.staged_native or not args.staged_sha256:
        manifest["anomalies"].append("staged_artifact_not_supplied")
        manifest["reason"] = "staged_artifact_not_supplied"
        Path(args.manifest).write_text(
            json.dumps(manifest, indent=2, sort_keys=True))
        print("CHALLENGE_WRAPPER_VERDICT=FAIL")
        return 1

    # Independently confirm the staged bytes match the declared digest before the
    # challenge is allowed to load them.
    try:
        actual = hashlib.sha256(
            pathlib.Path(args.staged_native).read_bytes()
        ).hexdigest()
        manifest["staged_sha256_verified"] = actual
        if actual != args.staged_sha256:
            manifest["anomalies"].append("staged_sha_mismatch_on_disk")
    except Exception as exc:
        manifest["anomalies"].append(f"staged_unreadable:{type(exc).__name__}")

    cache = pathlib.Path("/tmp/moe-challenge-worker")
    if cache.exists():
        shutil.rmtree(cache)
    cache.mkdir(parents=True)
    os.chown(cache, args.worker_uid, args.worker_uid)
    os.chmod(cache, 0o700)

    env = dict(os.environ)
    env["MOE_STAGED_NATIVE"] = args.staged_native
    env["MOE_STAGED_SHA256"] = args.staged_sha256
    env["MOE_EXPECT_UID"] = str(args.worker_uid)
    env["HOME"] = str(cache)
    env["TMPDIR"] = str(cache)
    env["TRITON_HOME"] = str(cache)
    env["TRITON_CACHE_DIR"] = str(cache / "triton")
    env["XDG_CACHE_HOME"] = str(cache / "xdg")

    out = ""
    try:
        proc = subprocess.run(
            ["setpriv", f"--reuid={args.worker_uid}",
             f"--regid={args.worker_uid}", "--init-groups", "--no-new-privs",
             "--", sys.executable, "-I", CHALLENGE],
            cwd="/tmp", env=env,
            timeout=1800, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True,
        )
        manifest["child_launched"] = True
        manifest["exit_code"] = proc.returncode
        out = proc.stdout or ""
    except subprocess.TimeoutExpired as exc:
        manifest["child_launched"] = True
        manifest["anomalies"].append("timeout")
        out = exc.stdout if isinstance(exc.stdout, str) else ""
    except OSError as exc:
        manifest["anomalies"].append(f"spawn_failed:{type(exc).__name__}")

    (log_dir / "challenge-moe-permute.log").write_text(out)

    if "CHALLENGE_MOE_PERMUTE=PASS" not in out:
        manifest["anomalies"].append("pass_marker_absent")
    if f"CHALLENGE_STAGED_SHA256={args.staged_sha256}" not in out:
        manifest["anomalies"].append("staged_sha_not_reported")

    # Structural completeness must come from the emitted JSON, not from stdout
    # shape alone: locate the object carrying the completeness block.
    completeness = None
    for start in range(len(out)):
        if out[start] != "{":
            continue
        for end in range(len(out), start, -1):
            if out[end - 1] != "}":
                continue
            try:
                obj = json.loads(out[start:end])
            except Exception:
                continue
            if isinstance(obj, dict) and "completeness" in obj:
                completeness = obj["completeness"]
                manifest["failures_reported"] = obj.get("failures")
            break
        if completeness is not None:
            break

    if completeness is None:
        manifest["anomalies"].append("completeness_block_absent")
    else:
        manifest["completeness"] = completeness
        req = set(completeness.get("required_scenarios") or [])
        obs = set(completeness.get("observed_scenarios") or [])
        if not req:
            manifest["anomalies"].append("required_scenarios_empty")
        if req != obs:
            manifest["anomalies"].append("scenario_set_mismatch")
        if completeness.get("missing_scenarios"):
            manifest["anomalies"].append("missing_scenarios")
        if completeness.get("extra_scenarios"):
            manifest["anomalies"].append("extra_scenarios")
        counts = completeness.get("call_counts") or {}
        if counts.get("check_case") != completeness.get(
            "expected_check_case_calls"
        ):
            manifest["anomalies"].append("check_case_call_count")
        if counts.get("check_scaling") != 1:
            manifest["anomalies"].append("check_scaling_call_count")
        if completeness.get("staged_native_sha256") != args.staged_sha256:
            manifest["anomalies"].append("completeness_sha_mismatch")

    ok = bool(
        manifest["child_launched"]
        and manifest["exit_code"] == 0
        and not manifest["anomalies"]
    )
    manifest["verdict"] = "PASS" if ok else "FAIL"
    manifest["reason"] = (
        "all_required_scenarios_satisfied" if ok
        else "; ".join(manifest["anomalies"]) or "challenge_failed"
    )
    Path(args.manifest).write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"CHALLENGE_WRAPPER_VERDICT={manifest['verdict']}")
    print(f"CHALLENGE_WRAPPER_REASON={manifest['reason']}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
