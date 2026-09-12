#!/usr/bin/env python3
"""Behavioral verifier for INT8 per-token-group quantization with frozen baseline.

TRUSTED PARENT/WORKER BOUNDARY:
This verifier runs as root. It spawns the candidate validation as a non-root
worker (uid 65534) via subprocess, captures the worker's structured output over
a pipe, and writes reward.txt itself. The worker never touches /logs/verifier.

FROZEN TRITON BASELINE:
The performance baseline is reference_int8_utils.py, a BYTE-IDENTICAL copy of
vllm/model_executor/layers/quantization/utils/int8_utils.py at the task base commit
(SHA-256 36406a44b95e54cf99988105d0fe9a69645a0d2fcbfe2e60b1982d3ac9fdcff3, verifiable
against upstream git history). It is installed by the verifier, after the agent phase, root-owned and read-only
under /opt/ai-infra-bench/reference-int8/, so the candidate
cannot modify the baseline, the threshold, or the timing protocol. It is loaded through
frozen_reference_loader.py in a subprocess whose sys.path excludes /workspace/repo.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback


WORKER_CODE = r'''
import argparse
import contextlib
import json
import statistics
import sys
import traceback

import torch

PAYLOAD_BEGIN = "---WORKER-PAYLOAD-BEGIN---"
PAYLOAD_END = "---WORKER-PAYLOAD-END---"

def emit_result(result: dict) -> None:
    """Print the worker result with framing markers.

    Importing vllm emits Triton/CUDA log lines on stdout, so the parent must not
    assume stdout is pure JSON. Delimit the payload so the parent can extract it.
    """
    print(PAYLOAD_BEGIN)
    print(json.dumps(result, indent=2, sort_keys=True))
    print(PAYLOAD_END)
    sys.stdout.flush()


def cuda_quant(x, group_size, eps=1e-10, int8_min=-128.0, int8_max=127.0):
    """Invoke the candidate CUDA operator."""
    q = torch.empty_like(x, dtype=torch.int8)
    s = torch.empty(
        x.shape[:-1] + (x.shape[-1] // group_size,),
        device=x.device,
        dtype=torch.float32,
    )
    torch.ops._C.per_token_group_quant_int8(x, q, s, group_size, eps, int8_min, int8_max)
    return q, s


def reference(x, group_size, eps=1e-10, int8_min=-128, int8_max=127):
    """Pure PyTorch reference for correctness validation."""
    g = x.float().reshape(-1, group_size)
    s = g.abs().amax(dim=1).clamp_min(eps) / float(int8_max)
    q = torch.clamp(torch.round(g / s[:, None]), int8_min, int8_max).to(torch.int8)
    return q.reshape_as(x), s.reshape(x.shape[:-1] + (x.shape[-1] // group_size,))


def timed_ms(fn, warmup=40, repeats=400):
    """Time a GPU operation using CUDA events."""
    for _ in range(warmup):
        fn()
    torch.cuda.synchronize()
    samples = []
    for _ in range(5):
        begin, end = torch.cuda.Event(True), torch.cuda.Event(True)
        begin.record()
        for _ in range(repeats):
            fn()
        end.record()
        end.synchronize()
        samples.append(begin.elapsed_time(end) / repeats)
    return statistics.median(samples)


@contextlib.contextmanager
def replace(module, name, value):
    """Temporarily replace a module attribute."""
    old = getattr(module, name)
    setattr(module, name, value)
    try:
        yield
    finally:
        setattr(module, name, old)


class _Platform:
    """Proxy the production platform interface for the dispatch-only ROCm probe."""
    def __init__(self, original):
        self._original = original

    def is_cuda(self):
        return False

    def is_rocm(self):
        return True

    def is_cuda_alike(self):
        return True

    def is_cpu(self):
        return False

    def __getattr__(self, name):
        return getattr(self._original, name)


def check_correctness() -> dict:
    """Validate CUDA operator correctness against PyTorch reference."""
    from vllm.model_executor.layers.quantization.utils import int8_utils

    torch.manual_seed(21476)
    cases = [
        ((32, 128), 64, torch.float16),
        ((64, 256), 128, torch.bfloat16),
        ((7, 512), 64, torch.float32),
        ((2, 3, 256), 32, torch.float16),
    ]

    results = []
    for shape, group_size, dtype in cases:
        x = (torch.randn(shape, device="cuda", dtype=dtype) * 8).contiguous()

        # Independent numerical reference; no private candidate helper is required.
        rq, rs = reference(x, group_size)
        cq, cs = cuda_quant(x, group_size)
        cuda_q_delta = (cq.to(torch.int16) - rq.to(torch.int16)).abs().max().item()
        assert cuda_q_delta <= 1, "CUDA differs from independent reference by >1"
        cuda_reference_delta = cuda_q_delta
        assert torch.allclose(cs, rs, rtol=2e-4, atol=2e-5), "CUDA reference scale mismatch"
        ts = rs

        results.append({
            "shape": shape,
            "group_size": group_size,
            "dtype": str(dtype),
            "cuda_q_delta": int(cuda_q_delta),
            "cuda_reference_delta": int(cuda_reference_delta),
            "scale_reference_close": True,
            "scale_max_delta": float((cs - ts).abs().max().item()),
        })

    return {"cases": results}


def check_public_dispatch() -> dict:
    """Observe native dispatch and real Triton launches without private names."""
    from vllm.model_executor.layers.quantization.utils import int8_utils
    from triton.runtime.jit import JITFunction

    x = torch.randn((4, 128), device="cuda", dtype=torch.float16).contiguous()
    rq, rs = reference(x, 64)
    original_run = JITFunction.run
    launches = []

    def observe_run(kernel, *args, **kwargs):
        launches.append(type(kernel).__name__)
        return original_run(kernel, *args, **kwargs)

    with replace(JITFunction, "run", observe_run):
        with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU]) as prof:
            q, s = int8_utils.per_token_group_quant_int8(x, 64)
        native_seen = any(event.key == "_C::per_token_group_quant_int8"
                          for event in prof.key_averages())
        assert native_seen, "CUDA public wrapper did not dispatch the public native operator"
        assert not launches, "CUDA public wrapper selected the Triton fallback"
        assert (q.to(torch.int16) - rq.to(torch.int16)).abs().max().item() <= 1
        assert torch.allclose(s, rs, rtol=2e-4, atol=2e-5)

        # Hardware remains CUDA for numerical execution. Only the production
        # platform interface is varied to test the fallback decision.
        with replace(int8_utils, "current_platform", _Platform(int8_utils.current_platform)):
            with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU]) as prof:
                fq, fs = int8_utils.per_token_group_quant_int8(x, 64)
        assert launches, "non-CUDA dispatch did not execute the Triton fallback"
        assert not any(event.key == "_C::per_token_group_quant_int8"
                       for event in prof.key_averages()), "fallback called the native CUDA operator"
    assert (fq.to(torch.int16) - rq.to(torch.int16)).abs().max().item() <= 1
    assert torch.allclose(fs, rs, rtol=2e-4, atol=2e-5)
    return {"cuda_dispatch": "native", "non_cuda_dispatch": "triton"}


def check_configurable_arguments() -> dict:
    """Verify native operator accepts configurable eps/int8_min/int8_max."""
    cases = [
        (torch.zeros((3, 64), device="cuda", dtype=torch.float32), 64, 1e-3, -64, 63),
        (
            torch.tensor(
                [[-4.0, -1.0, 0.0, 1.0, 4.0] * 16],
                device="cuda",
                dtype=torch.float16,
            ).contiguous(),
            80,
            1e-6,
            -32,
            31,
        ),
    ]

    results = []
    for x, group_size, eps, lower, upper in cases:
        q, s = cuda_quant(x, group_size, eps, float(lower), float(upper))
        rq, rs = reference(x, group_size, eps, lower, upper)

        assert int(q.min()) >= lower and int(q.max()) <= upper
        assert (q.to(torch.int16) - rq.to(torch.int16)).abs().max().item() <= 1
        assert torch.allclose(s, rs, rtol=2e-4, atol=2e-5)

        results.append({
            "shape": list(x.shape),
            "group_size": group_size,
            "eps": eps,
            "range": [lower, upper],
        })

    return {"cases": results}


def worker_main():
    """Worker subprocess: validate candidate and emit structured JSON."""
    import importlib.util

    # Explicitly load candidate vllm._C extension before accessing torch.ops._C
    spec = importlib.util.find_spec("vllm._C")
    if not spec or not spec.origin:
        result = {
            "verdict": "FAIL",
            "reason": "extension_not_found",
            "spec": str(spec),
        }
        emit_result(result)
        sys.exit(1)

    torch.ops.load_library(spec.origin)

    result = {
        "verdict": "FAIL",
        "stages": {},
        "frozen_baseline_used": True,
        "parent_worker_boundary": True,
    }

    try:
        assert torch.cuda.is_available(), "GPU not available"

        result["gpu"] = torch.cuda.get_device_name(0)
        result["capability"] = torch.cuda.get_device_capability(0)

        # Stage 1: Verify native operator exists
        has_op = hasattr(torch.ops._C, "per_token_group_quant_int8")
        swapped_alias = hasattr(torch.ops._C, "per_token_group_int8_quant")

        if not has_op:
            result["reason"] = "native_operator_missing"
            result["swapped_alias"] = swapped_alias
            emit_result(result)
            sys.exit(1)

        result["stages"]["operator_surface"] = "PASS"

        # Stage 2: Correctness
        result["stages"]["correctness"] = check_correctness()

        # Stage 3: Public dispatch
        result["stages"]["public_dispatch"] = check_public_dispatch()

        # Stage 4: Configurable arguments
        result["stages"]["configurable_arguments"] = check_configurable_arguments()

        # Return actual values; the parent compares these with an isolated frozen run.
        sys.path.insert(0, "/tests")
        from quant_boundary import observe
        from vllm.model_executor.layers.quantization.utils.int8_utils import per_token_group_quant_int8
        boundary_inputs = json.load(sys.stdin)
        result["stages"]["precision_boundaries"] = {
            "native": observe(boundary_inputs["precision"], lambda x, g, eps: cuda_quant(x, g, eps, -128., 127.)),
            "public": observe(boundary_inputs["precision"], per_token_group_quant_int8),
        }

        from quant_ranges import observe as observe_ranges
        result["stages"]["configured_ranges"] = {"cases": observe_ranges(boundary_inputs["ranges"], cuda_quant)}

        # Stage 5: Performance vs frozen baseline (run by parent)
        result["verdict"] = "PASS_CORRECTNESS"
        result["performance_deferred_to_parent"] = True

        emit_result(result)
        sys.exit(0)

    except Exception as exc:
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc()
        emit_result(result)
        sys.exit(1)


if __name__ == "__main__":
    worker_main()
'''


PAYLOAD_BEGIN = "---WORKER-PAYLOAD-BEGIN---"
PAYLOAD_END = "---WORKER-PAYLOAD-END---"


def extract_worker_payload(stdout: str) -> tuple[str, str | None]:
    """Extract framed JSON payload from worker stdout.

    Returns (payload_text, error_reason). If extraction succeeds, error_reason is None.
    If the frame markers are missing or malformed, returns ("", error_reason).
    """
    begins = stdout.count(PAYLOAD_BEGIN)
    ends = stdout.count(PAYLOAD_END)
    if begins != 1 or ends != 1:
        return "", "worker_payload_frame_count"
    body = stdout.split(PAYLOAD_BEGIN, 1)[1].split(PAYLOAD_END, 1)[0]
    return body, None


# The parent requires exactly these stages in the worker payload. Missing, extra,
# malformed, or duplicated stages are all treated as failures. Stage 5
# (performance) is deliberately absent: the parent runs it itself.
WORKER_REQUIRED_STAGES = {
    "operator_surface",
    "correctness",
    "public_dispatch",
    "configurable_arguments",
    "precision_boundaries",
    "configured_ranges",
}


FROZEN_DIR = "/opt/ai-infra-bench/reference-int8"

# Both files are part of the trusted baseline: the reference holds the kernel, and
# the loader decides which kernel is handed back. Pinning only the reference would
# leave a loader rewrite free to substitute a deliberately slow baseline.
FROZEN_EXPECTED_SHA256 = {
    "reference_int8_utils.py":
        "36406a44b95e54cf99988105d0fe9a69645a0d2fcbfe2e60b1982d3ac9fdcff3",
    "frozen_reference_loader.py":
        "cbe0ace52fb119b73270d87573fab94ca7d85a0d4ac7d376aafd014d3ac546e3",
}


def verify_frozen_baseline(stage: str) -> dict:
    """Fail-closed SHA-256 check of every trusted baseline file.

    Called by the parent before and after the worker, and again before and after
    the timing loop, so a mutation at any point in the run is caught rather than
    only one taken before the verifier started.
    """
    import hashlib
    import pathlib

    observed = {}
    for name, expected in FROZEN_EXPECTED_SHA256.items():
        path = pathlib.Path(FROZEN_DIR) / name
        if not path.exists():
            raise RuntimeError(
                f"frozen baseline missing at stage={stage}: {path}"
            )
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(
                f"frozen baseline tampered at stage={stage}: {name} "
                f"expected {expected}, got {actual}"
            )
        observed[name] = actual
    return observed


def correctness_observations_complete(stages):
    import math
    if stages.get("operator_surface") != "PASS":
        return False
    if stages.get("public_dispatch") != {"cuda_dispatch": "native",
                                          "non_cuda_dispatch": "triton"}:
        return False
    cases = stages.get("correctness", {}).get("cases")
    expected = [([32, 128], 64, "torch.float16"),
                ([64, 256], 128, "torch.bfloat16"),
                ([7, 512], 64, "torch.float32"),
                ([2, 3, 256], 32, "torch.float16")]
    if not isinstance(cases, list) or len(cases) != len(expected):
        return False
    for record, (shape, group, dtype) in zip(cases, expected):
        if not isinstance(record, dict):
            return False
        if (record.get("shape"), record.get("group_size"), record.get("dtype")) != (shape, group, dtype):
            return False
        for key in ("cuda_q_delta", "cuda_reference_delta"):
            if type(record.get(key)) is not int or not 0 <= record[key] <= 1:
                return False
        delta = record.get("scale_max_delta")
        if (type(delta) not in (float, int) or not math.isfinite(delta)
                or delta < 0 or record.get("scale_reference_close") is not True):
            return False
    return stages.get("configurable_arguments") == {"cases": [
        {"shape": [3, 64], "group_size": 64, "eps": 1e-3, "range": [-64, 63]},
        {"shape": [1, 80], "group_size": 80, "eps": 1e-6, "range": [-32, 31]},
    ]}


def run_worker(boundary_inputs, boundary_expected) -> dict:
    """Spawn the validation worker as uid 65534 (nobody), capture structured output."""
    try:
        result = subprocess.run(
            ["runuser", "-u", "nobody", "--", "python3", "-I", "-c", WORKER_CODE],
            input=json.dumps(boundary_inputs),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=600,
            check=False,
            text=True,
        )
    except subprocess.TimeoutExpired:
        return {
            "verdict": "FAIL",
            "reason": "worker_timeout",
            "timeout_sec": 600,
        }
    except Exception as exc:
        return {
            "verdict": "FAIL",
            "reason": "worker_spawn_failed",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }

    if result.returncode == 0:
        payload_text, extract_error = extract_worker_payload(result.stdout)
        if extract_error:
            return {
                "verdict": "FAIL",
                "reason": extract_error,
                "stdout": result.stdout[:2000],
                "stderr": result.stderr[:2000],
            }
        try:
            worker_output = json.loads(payload_text)
            if worker_output.get("verdict") != "PASS_CORRECTNESS":
                return {
                    "verdict": "FAIL",
                    "reason": "worker_verdict_not_pass",
                    "worker_output": worker_output,
                }

            # A zero exit and a PASS verdict are necessary but not sufficient: the
            # parent independently re-checks that every required stage ran and
            # reported a well-formed result, so an early success cannot skip work.
            stages = worker_output.get("stages")
            if not isinstance(stages, dict):
                return {
                    "verdict": "FAIL",
                    "reason": "worker_stages_malformed",
                    "stages_type": type(stages).__name__,
                    "worker_output": worker_output,
                }

            observed = set(stages)
            missing = WORKER_REQUIRED_STAGES - observed
            unexpected = observed - WORKER_REQUIRED_STAGES
            if missing or unexpected:
                return {
                    "verdict": "FAIL",
                    "reason": "incomplete_stage_coverage",
                    "missing_stages": sorted(missing),
                    "unexpected_stages": sorted(unexpected),
                    "executed_stages": sorted(observed),
                }

            malformed = sorted(
                name for name, value in stages.items()
                if value is None
                or (isinstance(value, (dict, str)) and not value)
                or not isinstance(value, (dict, str))
            )
            if malformed:
                return {
                    "verdict": "FAIL",
                    "reason": "stage_result_malformed",
                    "malformed_stages": malformed,
                }

            # Guard against a worker that prints a partial payload before the real
            # one; the payload framing ensures only one complete JSON object is parsed.
            if payload_text.count('"operator_surface"') != 1:
                return {
                    "verdict": "FAIL",
                    "reason": "duplicate_or_missing_stage_key",
                    "operator_surface_occurrences":
                        payload_text.count('"operator_surface"'),
                }

            if not correctness_observations_complete(stages):
                return {"verdict": "FAIL", "reason": "correctness_observations_incomplete"}
            from quant_boundary import compare
            observations = stages.get("precision_boundaries", {})
            errors = {path: compare(observations.get(path), boundary_expected["precision"])
                      for path in ("native", "public")}
            if any(errors.values()):
                return {"verdict": "FAIL", "reason": "precision_boundary_mismatch", "errors": errors}
            from quant_ranges import compare as compare_ranges
            range_errors = compare_ranges(stages.get("configured_ranges", {}).get("cases"), boundary_expected["ranges"])
            if range_errors:
                return {"verdict": "FAIL", "reason": "configured_range_mismatch", "errors": range_errors}
            return worker_output
        except (ValueError, TypeError, AttributeError) as exc:
            return {
                "verdict": "FAIL",
                "reason": "worker_output_invalid_json",
                "error": str(exc),
                "stdout": result.stdout[:2000],
                "stderr": result.stderr[:2000],
            }
    else:
        payload_text, extract_error = extract_worker_payload(result.stdout)
        if extract_error:
            return {
                "verdict": "FAIL",
                "reason": "worker_failed_unparseable",
                "worker_exit": result.returncode,
                "extract_error": extract_error,
                "stdout": result.stdout[:2000],
                "stderr": result.stderr[:2000],
            }
        try:
            worker_output = json.loads(payload_text)
            return {
                "verdict": "FAIL",
                "reason": "worker_exit_nonzero",
                "worker_exit": result.returncode,
                "worker_output": worker_output,
                "stderr": result.stderr[:2000],
            }
        except json.JSONDecodeError:
            return {
                "verdict": "FAIL",
                "reason": "worker_failed_unparseable",
                "worker_exit": result.returncode,
                "stdout": payload_text[:2000],
                "stderr": result.stderr[:2000],
            }


def run_frozen_baseline_subprocess(
    shape: tuple, group_size: int, snapshot_path: str, snapshot_sha256: str
) -> float:
    """Time the frozen Triton baseline in a subprocess that excludes /workspace/repo.

    The input is the parent-generated snapshot, not a locally re-seeded tensor, so
    candidate and baseline are measured on provably identical bytes rather than on
    an assumption about cross-process RNG reproducibility.
    """
    baseline_code = '''
import sys
# Remove /workspace/repo from sys.path so the frozen reference resolves triton from
# root-owned site-packages and never from candidate-authored files.
sys.path = [p for p in sys.path if not p.startswith("/workspace/repo")]

import hashlib
import statistics
import torch

# Load the frozen reference through its root-owned loader. The loader verifies the
# reference SHA-256 and installs stub vllm.* modules, so the byte-identical
# base-commit copy of int8_utils.py imports nothing the candidate controls.
sys.path.insert(0, "/opt/ai-infra-bench/reference-int8")
from frozen_reference_loader import load_frozen_reference

frozen_triton_quant = load_frozen_reference().per_token_group_quant_int8

group_size = ''' + str(group_size) + '''
snapshot_path = ''' + repr(snapshot_path) + '''
expected_snapshot_sha256 = ''' + repr(snapshot_sha256) + '''

# Load the immutable, parent-generated input and re-verify its digest here, so a
# swapped snapshot cannot quietly change what the baseline is timed on.
with open(snapshot_path, "rb") as handle:
    raw = handle.read()
actual_snapshot_sha256 = hashlib.sha256(raw).hexdigest()
if actual_snapshot_sha256 != expected_snapshot_sha256:
    raise SystemExit(
        "input snapshot digest mismatch: expected "
        + expected_snapshot_sha256 + ", got " + actual_snapshot_sha256
    )

x = torch.load(snapshot_path, map_location="cuda").contiguous()

# Warmup
for _ in range(40):
    frozen_triton_quant(x, group_size)

torch.cuda.synchronize()

# Time
samples = []
for _ in range(5):
    begin = torch.cuda.Event(True)
    end = torch.cuda.Event(True)
    begin.record()
    for _ in range(400):
        frozen_triton_quant(x, group_size)
    end.record()
    end.synchronize()
    samples.append(begin.elapsed_time(end) / 400)

print(statistics.median(samples))
'''

    try:
        result = subprocess.run(
            ["python3", "-I", "-c", baseline_code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
            check=True,
            text=True,
        )
        return float(result.stdout.strip())
    except Exception as exc:
        raise RuntimeError(f"Frozen baseline failed for {shape}: {exc}")


def stage_candidate_native():
    """Freeze a regular candidate library without importing candidate Python."""
    import hashlib
    import pathlib
    import stat
    import tempfile
    root = pathlib.Path("/workspace/repo").resolve()
    candidates = list((root / "vllm").glob("_C*.so"))
    candidates = [p for p in candidates if p.name.startswith(("_C.", "_C_"))]
    if len(candidates) != 1:
        raise RuntimeError(f"expected one native _C library, found {candidates}")
    source = candidates[0]
    if root not in source.resolve().parents:
        raise RuntimeError("candidate native library escapes repository")
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise RuntimeError("candidate native library is not regular")
        data = stream.read()
    parent = pathlib.Path("/trusted/int8")
    parent.mkdir(parents=True, exist_ok=True)
    directory = pathlib.Path(tempfile.mkdtemp(prefix="native-", dir=parent))
    os.chmod(directory, 0o755)
    target = directory / source.name
    target.write_bytes(data)
    os.chmod(target, 0o444)
    return str(target), hashlib.sha256(data).hexdigest()


def run_candidate_timing(native, native_sha, shape, group, snapshot, snapshot_sha):
    import math
    import pathlib
    import statistics
    child = pathlib.Path(__file__).resolve().with_name("candidate_timing.py")
    result = subprocess.run(
        ["runuser", "-u", "nobody", "--", "python3", "-I", str(child),
         native, native_sha, snapshot, snapshot_sha, str(group)],
        cwd="/", capture_output=True, text=True, timeout=180, check=False,
    )
    if result.returncode:
        raise RuntimeError(f"candidate timing exit={result.returncode}: "
                           + result.stderr[-2000:])
    frames = [line[len("INT8_TIMING="):] for line in result.stdout.splitlines()
              if line.startswith("INT8_TIMING=")]
    if len(frames) != 1:
        raise RuntimeError("candidate timing did not emit exactly one completion record")
    record = json.loads(frames[0])
    for key, expected in {
        "shape": list(shape), "group_size": group, "warmup": 40,
        "iterations": 400, "repeats": 5, "native_sha256": native_sha,
        "input_sha256": snapshot_sha, "actual_uid": 65534,
    }.items():
        if record.get(key) != expected:
            raise RuntimeError(f"candidate timing observation mismatch: {key}")
    samples = record.get("samples_ms")
    if (not isinstance(samples, list) or len(samples) != 5 or not all(
        type(value) in (float, int) and math.isfinite(value) and value > 0
        for value in samples
    )):
        raise RuntimeError("candidate timing samples incomplete or invalid")
    return statistics.median(samples), record


def check_performance_vs_frozen_baseline(worker_output: dict) -> dict:
    """Parent compares isolated candidate timings to the frozen baseline."""
    import torch
    import math
    pre_timing_sha256 = verify_frozen_baseline("pre_timing")
    native, native_sha = stage_candidate_native()

    cases = [
        ((1024, 4096), 128),
        ((4096, 4096), 128),
        ((2048, 4096), 64),
        ((16, 256, 4096), 128),
        ((4096, 4096), 64),
    ]

    # Root-owned, read-only snapshots are shared with the unprivileged timing
    # child. Both measurements use identical bytes; only the parent may replace
    # or remove snapshots.
    import hashlib
    import pathlib
    import shutil

    snapshot_dir = pathlib.Path(FROZEN_DIR).parent / "perf-inputs"
    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)
    snapshot_dir.mkdir(mode=0o755, parents=False)
    os.chmod(snapshot_dir, 0o755)

    speedups = []
    timing_results = []

    try:
        for trial, (shape, group_size) in enumerate(cases):
            # Generate the input once, in the trusted parent.
            torch.manual_seed(21476 + trial)
            x = (torch.randn(shape, device="cuda", dtype=torch.bfloat16) * 8).contiguous()

            snapshot_path = snapshot_dir / f"input-{trial}.pt"
            torch.save(x, snapshot_path)
            os.chmod(snapshot_path, 0o444)
            snapshot_sha256 = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()

            # Time the candidate on the snapshot's own bytes, reloaded the same way
            # the baseline subprocess loads them.
            del x
            cuda_ms, candidate_record = run_candidate_timing(
                native, native_sha, shape, group_size,
                str(snapshot_path), snapshot_sha256,
            )

            # Time the frozen baseline in an isolated subprocess on the same bytes.
            frozen_ms = run_frozen_baseline_subprocess(
                shape, group_size, str(snapshot_path), snapshot_sha256
            )

            if not math.isfinite(frozen_ms) or frozen_ms <= 0:
                raise RuntimeError("invalid frozen baseline timing")
            speedup = frozen_ms / cuda_ms
            speedups.append(speedup)

            timing_results.append({
                "shape": shape,
                "group_size": group_size,
                "candidate_observation": candidate_record,
                "candidate_cuda_ms": round(cuda_ms, 6),
                "frozen_triton_ms": round(frozen_ms, 6),
                "speedup": round(speedup, 3),
                "input_snapshot_sha256": snapshot_sha256,
            })
    finally:
        shutil.rmtree(snapshot_dir, ignore_errors=True)
        shutil.rmtree(pathlib.Path(native).parent, ignore_errors=True)

    min_speedup = min(speedups)
    performance_pass = min_speedup >= 1.5

    # Re-verify after timing so a mutation landed mid-run is caught too.
    post_timing_sha256 = verify_frozen_baseline("post_timing")

    return {
        "timing": timing_results,
        "min_speedup": round(min_speedup, 3),
        "threshold": 1.5,
        "performance_pass": performance_pass,
        "frozen_reference_verified": {
            "pre_timing": pre_timing_sha256,
            "post_timing": post_timing_sha256,
        },
    }


def main():
    """Trusted parent: run worker, check performance, write reward."""
    print("vllm-int8-per-token-group-quantization verifier (parent/worker + frozen baseline)")

    # Gate the baseline before any candidate code runs in this verifier. The
    # native rebuild in test.sh already executed candidate build code by now, so
    # this is the first parent-side observation of the trusted files.
    try:
        pre_worker_sha256 = verify_frozen_baseline("pre_worker")
    except RuntimeError as exc:
        verdict = {
            "verdict": "FAIL",
            "reason": "frozen_baseline_integrity",
            "stage": "pre_worker",
            "error": str(exc),
        }
        print(json.dumps(verdict, indent=2))
        with open("/logs/verifier/reward.txt", "w") as f:
            f.write("0\n")
        sys.exit(1)

    # Run worker for correctness checks
    sys.path.insert(0, "/tests")
    from quant_boundary import cases, frozen_observations
    from quant_ranges import cases as range_cases, frozen_observations as frozen_ranges
    boundary_inputs = {"precision": cases(), "ranges": range_cases()}
    boundary_expected = {
        "precision": frozen_observations(boundary_inputs["precision"], FROZEN_DIR),
        "ranges": frozen_ranges(boundary_inputs["ranges"], FROZEN_DIR),
    }
    worker_result = run_worker(boundary_inputs, boundary_expected)

    # The worker just ran candidate code as nobody; re-verify before trusting any
    # subsequent timing.
    try:
        post_worker_sha256 = verify_frozen_baseline("post_worker")
    except RuntimeError as exc:
        verdict = {
            "verdict": "FAIL",
            "reason": "frozen_baseline_integrity",
            "stage": "post_worker",
            "error": str(exc),
            "worker_result": worker_result,
        }
        print(json.dumps(verdict, indent=2))
        with open("/logs/verifier/reward.txt", "w") as f:
            f.write("0\n")
        sys.exit(1)

    if worker_result["verdict"] != "PASS_CORRECTNESS":
        verdict = {
            "verdict": "FAIL",
            "worker_result": worker_result,
        }
        print(json.dumps(verdict, indent=2))
        with open("/logs/verifier/reward.txt", "w") as f:
            f.write("0\n")
        sys.exit(1)

    # Parent runs performance check vs frozen baseline
    try:
        perf_result = check_performance_vs_frozen_baseline(worker_result)
        worker_result["stages"]["performance_vs_frozen_baseline"] = perf_result

        if not perf_result["performance_pass"]:
            verdict = {
                "verdict": "FAIL",
                "reason": "performance_below_threshold",
                "stages": worker_result["stages"],
            }
            print(json.dumps(verdict, indent=2))
            with open("/logs/verifier/reward.txt", "w") as f:
                f.write("0\n")
            sys.exit(1)

        # All checks pass
        verdict = {
            "verdict": "PASS",
            "stages": worker_result["stages"],
            "frozen_baseline_integrity": {
                "pre_worker": pre_worker_sha256,
                "post_worker": post_worker_sha256,
            },
        }
        print(json.dumps(verdict, indent=2))
        with open("/logs/verifier/reward.txt", "w") as f:
            f.write("1\n")
        sys.exit(0)

    except Exception as exc:
        verdict = {
            "verdict": "FAIL",
            "reason": "performance_check_failed",
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "worker_result": worker_result,
        }
        print(json.dumps(verdict, indent=2))
        with open("/logs/verifier/reward.txt", "w") as f:
            f.write("0\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
