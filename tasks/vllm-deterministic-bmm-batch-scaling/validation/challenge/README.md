# Independent challenge

The formal verifier covers eight numerical shapes, seven invalid-input cases, output-copy compatibility and batch-independent launches. The independent challenge uses eight different shapes, including FP32 reductions at K=2048 and K=3072, plus empty non-batch dimensions, singleton dimensions and strided buffers. Batch=0 is not required because the frozen Base rejects an empty stack. Numerical accuracy and bitwise batch invariance are separate requirements.

Run `challenge_bmm.py` on an A100 in the pinned image after applying the selected patch to `/workspace/repo`. Oracle and the persistent-kernel alternative must pass. Base must fail the launch/precision checks, and the retained TF32-loss control must fail the long-reduction tolerance despite passing the short cases. Commands, inputs, outcomes and hashes are recorded in `../e2e-evidence.json`.
