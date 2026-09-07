# Environment sources and lock rationale

The candidate source is the exact parent commit of vLLM PR 35781:
`d88f28da05b12bc7d63ebe3dcedf445ecb274343`. Its public codeload archive is
locked by SHA-256 and size, and the reconstructed synthetic repository must
match upstream Git tree `037cc4e534167733500093aa225de6ab64a1028e`.

The closest official runtime is the vLLM v0.17.1 x86_64 CPU image, pinned to
platform manifest
`sha256:d19978a2d4bb2289c740a6c89d4cc15fbcf4d20d916f1e268168b8bbad3b776b`.
It supplies Python 3.12.13, PyTorch 2.10.0+cpu and vLLM's CPU native extension.
Candidate Python source comes only from the locked base archive. Compiled
extensions and generated `_version.py` are copied to exact paths under
`/app/vllm`; other wheel Python source is not overlaid. Build and runtime smoke
checks prove that both `vllm.__file__` and `vllm._C` resolve under `/app`.

The PR changes Python scheduler behavior, so reusing the nearest official CPU
extension is a deliberate simplification. It remains an ABI risk and must not
be generalized to tasks that change native code. Those tasks require an exact
source rebuild with native input locks.

The official v0.17.1 CPU image's `_C_AVX2` shared object does not expose a
Python `PyInit__C_AVX2` entry point when imported directly. The unmodified
official image exhibits the same behavior; vLLM's CPU platform catches it and
continues. Scheduler baseline validation does not exercise AVX2 inference, so
this environment is not evidence of full CPU model-execution compatibility.

Runtime is offline and must be launched with `--network none`. The baseline is
CPU deterministic: it counts production scheduler remote-KV callbacks and
waiting-queue occupancy during idle rounds. A GPU-2 launch on the A100 host is
performed only to prove the declared CPU workload is not silently presented as
a CUDA workload and that the requested validation hardware is visible.
