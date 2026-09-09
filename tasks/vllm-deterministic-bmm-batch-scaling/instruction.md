I am using `bmm_batch_invariant` for deterministic 3-D batched matrix
multiplication. On an A100, its launch overhead grows with the batch because
the current Python path starts one matrix multiplication per batch item.
Please remove that per-item launch pattern and handle the batch with a
batch-aware deterministic Triton kernel.

The result must remain bitwise identical between one batched call and the
concatenation of equivalent single-batch calls for FP16, BF16, and FP32 inputs.
Preserve numerical agreement with `torch.bmm`, the identity and contents of an
`out=` tensor, input dtype and device validation, and existing shape errors.
Preserve the existing output-copy semantics: an `out` tensor may have a different
dtype or reside on the CPU, with the result converted into that destination.
Broadcast-compatible destinations remain valid; incompatible destination shapes
must still fail. The returned object must be the supplied `out` tensor. Use
`rtol=2e-2` and `atol=2e-2` for the `torch.bmm` comparison; the
batch-versus-single comparison remains bitwise exact.

Work in `/workspace/repo`. To make the performance target concrete, use one
NVIDIA A100-SXM4-40GB with shapes `(8, 512, 512, 2560)`,
`(32, 512, 512, 2560)`, and `(8, 1280, 1280, 2560)`. Run five warmups, 20
iterations, and five median rounds. The new path must materially outperform
the original per-batch launch pattern on these representative shapes; for
`(8, 512, 512, 2560)`, it must be at least `2.0x` faster, and the other two shapes must be at
least `1.05x` faster. Internal function and
kernel names are up to you as long as the observable correctness, errors,
launch scaling, and performance remain intact.
