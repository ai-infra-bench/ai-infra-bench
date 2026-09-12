# vLLM request lifecycle retention

Fix completed requests retaining multimodal payloads while preserving streaming sessions and prefix-cache behavior. See [instruction.md](instruction.md).

The offline CPU image contains the exact Base source and the pinned donor's real AVX2 extension. Minimal distribution metadata selects CpuPlatform; PATH exposes the existing virtual environment. No model download or GPU is needed for this Python ownership boundary.

The verifier constructs a real Scheduler, Request, encoder cache manager and KVCacheManager. Deterministic media shapes and model outputs replace only model computation. Normal completion enters through schedule/update_from_output; cancellation and stream continuation use their production entrypoints. Weak references check release and retention, real cache lookups check reuse, and a GC callback detects collections during the target lifecycle.

A root parent independently reads the worker's Linux RSS at nine checkpoints over four batches. It checks that the live workload occurred and that post-warmup retained memory does not accumulate. It does not require memory to return immediately to the OS. Candidate stdout alone cannot pass this check. This is bounded hardening against known bypasses, not a sandbox against arbitrary malicious code sharing the Python observation process; a candidate that simulates both memory activity and reports remains outside the security guarantee.

Run the local entrypoint matrix with `python3 tasks/vllm-request-lifecycle-leak/validation/run-local-matrix.py`. Run formal Oracle validation with `harbor run -p tasks/vllm-request-lifecycle-leak -a oracle`. Raw results and limitations are recorded in `validation/e2e-evidence.json`; older records do not certify this version. No image publication is implied by a local build.
