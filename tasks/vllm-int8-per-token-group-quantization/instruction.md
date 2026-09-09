I am profiling INT8 per-token-group quantization in vLLM on an A100. The CUDA
calls still use the Triton implementation, and that path has become a
bottleneck for the shapes below. Please add a native CUDA implementation and
route CUDA calls to `per_token_group_quant_int8` through vLLM's existing `_C`
operator namespace. Platforms that cannot use the native operator must keep the
current Triton fallback.

The operator must support contiguous FP16, BF16, and FP32 inputs along with
configurable group size, epsilon, and INT8 bounds. Its quantized values
may differ from the deterministic Triton/reference result by at most one
integer step, and its scales must remain numerically equivalent.

Work in `/workspace/repo`. After changing native sources, rebuild the candidate
`_C` extension from the repo (the build toolchain, CUDA dependencies, and the
standard `pip install --no-build-isolation --no-deps -e .` flow are available in
the environment) and validate against that freshly built extension. Keep the
public native operator name `per_token_group_quant_int8`.

For the performance check, use one NVIDIA A100-SXM4-40GB and first confirm
correctness. The BF16 timing cases are `(1024, 4096)/group=128`,
`(4096, 4096)/group=128`, `(2048, 4096)/group=64`,
`(16, 256, 4096)/group=128`, and `(4096, 4096)/group=64`. Give each path 40
warmups, then collect five medians of 400 calls. The native path must be at
least `1.5x` faster than the Triton path in every case.
