> Update: the subsequent [full visible-trajectory and saved-repository review](rollout-codex-r01-full-review.md) is complete. Fresh rebuild rewards are **1 / 0 / 0 / 1**, with **23/23** supplemental checks per candidate. The scope limitations below describe the earlier diagnostic stage.

# Codex / GPT-6 medium: four A100 attempts

The four requested model attempts are complete. Original Harbor rewards are **0 / 0 / 0 / 0**. All were stopped by an undisclosed seven-argument native ABI assumption in the verifier. Task 1.2.9 accepts both the output-parameter convention and the functional convention returning `(q, scales)` through the task-named registered Torch operator. Regrading the unchanged verifier-built libraries with the complete corrected scorer yields **1 / 0 / 0 / 1**. GPU0 and GPU3 were false negatives; GPU1 and GPU2 have independently valid configured-range failures.

## Experiment and evidence scope

- Original task **1.2.8**, revision `10517bbe64663bc350f31b88e3aec1ccc1e2ab7f`; model `gpt-6-astra`, explicit `medium`, Codex **0.153.4**, Harbor **0.22.0**. Native `turn_context` confirms the model and effort in all four trajectories. No immutable backend model revision was supplied.
- Four concurrent attempts on separate A100-SXM4-40GB devices, GPUs 0–3, each limited to 8 CPUs and 32 GiB. Base `14bf19e39f601163265b7c7d58d972b8a83d8896`; image `sha256:5dc453932b016a3b73fb9316cce43f251275197b7a6295bc970e3de7a2718593`.
- A100 `set_proxy` uses port 7890. Harbor's domain allowlist remains in place through a GOST forwarding chain. Model traffic succeeds; GitHub and a direct-proxy GitHub probe were blocked. This is not unrestricted agent networking.
- Full repository snapshots, tracked diffs, untracked archives, status, native sessions and verifier logs were captured. All six recorded files in each final-state manifest were SHA256-verified. Canonical and prepared task inputs remained unchanged.
- A minimal actual Codex collector smoke passed before the campaign, including a tool-created sentinel and matching captured hash. Earlier direct-network, missing companion-executable and host-gateway setup failures are separate smoke evidence, not extra task attempts.
- Review here covers experiment integrity, original failure attribution, final tracked production diffs and new CUDA sources, corrected full-scoring execution, and independent offset challenges. **It is not a claim of completed line-by-line review of all four trajectories, untracked test/benchmark files and ignored/generated artifacts.** Those complete archives remain available for a deeper audit.

## Results

| GPU / trial suffix | Original total minutes | Original Harbor reward | Corrected full scorer | Attribution | Minimum speedup in corrected scorer |
|---|---:|---:|---:|---|---:|
| 0 / `NytaXYm` | 53.2 | 0 | 1 | False negative: hidden out-parameter ABI | 3.000× |
| 1 / `jsbo3RN` | 47.3 | 0 | 0 | ABI gate invalid, but rejects valid positive INT8 lower bounds | Not reached |
| 2 / `qCt7jRv` | 46.5 | 0 | 0 | ABI gate invalid, but rejects valid positive INT8 lower bounds | Not reached |
| 3 / `ceaE7jY` | 46.0 | 0 | 1 | False negative: hidden out-parameter ABI | 2.776× |

All four original Harbor trials have `exception_info=null` and completed a successful native rebuild. The first failing call was `expected at most 5 argument(s) but received 7 argument(s)`. Only the operator-surface stage completed in the original correctness worker. Agent-reported test counts and timings are not substituted for verifier scores.

The corrected scorer was run against the **original verifier-built native libraries in retained containers**, with identical library hashes before and after. Original logs were not overwritten. This is a full-scoring diagnostic regrade, **not four new model attempts or four clean full-snapshot Harbor replays**. Input and output paths were redirected to separate diagnostic directories; the Triton cache environment matches `test.sh`. One earlier diagnostic omitted that cache environment and failed with `/nonexistent` permissions; it is excluded from candidate conclusions. An initial diagnostic found zero running containers; it is also not counted as a test.

All four candidates pass the independent **18/18** storage-offset cases: three dtypes × offsets 0/1/3 × public/native entrypoints. The native challenge uses the registered schema adapter; expected numerical values remain independent. This confirms the earlier contiguous-offset defect was not reproduced in these answers.

## Confirmed defects and repair

The statement requests `_C::per_token_group_quant_int8` and observable behavior but does not prescribe whether outputs are returned or preallocated. All four candidates implement the valid functional schema `(Tensor, int, float, int, int) -> (Tensor, Tensor)`. Both correctness and isolated performance code previously assumed the Oracle's seven-argument, void-returning schema. The new shared `native_interface.py` resolves these two public call conventions once, outside timing loops, and casts bound scalars according to the registered schema. It does not read candidate private helper names or alter candidate computations. Existing thresholds, test data, reference, image and Oracle are unchanged. Unrecognized conventions still require explicit fixture review; arbitrary ABI inference is not claimed.

GPU1 and GPU2 separately require `int8_min <= 0`. The existing valid case `float16-1-100` passes the frozen Triton computation but is rejected by those native guards. Positive bounds such as `[1,100]`, `[50,100]` and `[3,7]` are representable INT8 clipping intervals permitted by configurable bounds. GPU0/GPU3 handle them. No case was removed to improve pass rate.

## Validation of task 1.2.9

- Corrected complete scorer: two passing functional implementations, two correctly rejected range-restricting implementations; tests and native-library hashes unchanged throughout.
- Actual Oracle Harbor run: reward **1**, no exception, seven scoring stages completed, minimum speedup **2.336×**. Original out-parameter schema remains supported.
- The complete GPU0 production implementation is retained as `functional-native-kernel.patch`, an expected-pass regression control. It is rollout-derived development evidence, not held-out evaluation data.
- Actual functional positive-control Harbor run: reward **1**, no exception, all seven scoring stages complete; source patch applied from Base and rebuilt by the unmodified entrypoint. Inputs remained unchanged. Ordinary ccache entries were reused only after verifier start; no native library or build directory was injected.
- Historical 20-control results on 1.2.7/1.2.8 remain historical evidence; they are not relabeled as a newly executed 21-control matrix on 1.2.9.

Evidence archives and SHA256 identities are under [evidence/codex-r01](evidence/codex-r01/manifest.json). Original raw snapshots remain under `/data/codex-pr70-rollouts-20260918/codex-gpt6-medium-r01` on A100; diagnostics and controls are separate sibling directories. Four attempts are too few to estimate a general model pass rate.
