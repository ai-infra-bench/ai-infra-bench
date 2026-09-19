# Review remediation

This task keeps the original serving problem. Its contract is correct Mamba outputs and recurrent-state updates under FULL-CG, with eager, first-token, ordinary decode, and supported speculative behavior preserved. The statement does not prescribe metadata classes, repair locations, storage layouts, or host synchronization during input preparation.

The semantic boundary is: scheduled prompts with existing recurrent state → production scheduler, runner input preparation, backend factory, model layers, CUDA graph replay and real state kernels → generated tokens and the distributions returned on subsequent steps. The verifier uses the public `LLM.generate` interface. Local chunked prefill supplies the same prior-state, still-prefilling continuation that disaggregated decode can receive. NIXL transport, model downloads and tokenization do not determine this transition and are omitted. Every model weight, prompt and expected result is created during verification, outside the agent image.

| Review finding | Remediation | Verification |
| --- | --- | --- |
| Printed success plus exit 0 earns reward | A root scorer compares every candidate output vector with a private trusted eager result. Child stdout is diagnostic only. | Both Python exit mechanisms, the old success marker, and a complete fabricated numeric report are negative controls. |
| Image exposes target files and PR/Oracle hints | The image manifest contains only generic Base and native donor provenance. Rebuild from the pinned donor without introducing the old manifest in any layer. | Agent-user image and Git inspection; Docker history; new immutable image ID. |
| Toy arithmetic ignores production state addresses | Run real models through `LLM.generate`, including real recurrent kernels, subsequent outputs, multiple batches and request reuse. | Base, counts-only and corrupted state-address controls. |
| Abstract test subclass rejects valid repair locations | Enter through the production engine and its normal factories and input preparation. | Correct controls repair production subclasses, runner inputs, and the shared split operation. |
| Eager and accepted-token speculative paths missing | Separate eager and speculative serving cases; accepted drafts are exercised and compared to frozen Base eager speculative serving. | Eager and speculative breakage controls. |
| Undisclosed no-sync requirement | Remove `set_sync_debug_mode` and do not judge metadata preparation synchronization. Inspect actual CUDA graph launches only during generation. | An otherwise correct implementation that reads sequence lengths back to the host must pass. |
| Historical records contradict the final executable | Preserve the incoming records under `archive/`; current results and hashes live in `e2e-evidence.json`. | Final artifact audit and Harbor trials. |

The new mixed-batch challenge also exposed a gap in the historical Oracle: a genuine first-token prompt can share a shape-compatible batch with a one-token continuation. The captured decode graph cannot initialize that new request's state, and the mixed metadata can leave captured addresses stale. The revised Oracle routes such fresh-state batches through the existing prefill path while retaining graph execution for stateful decode. The historical Oracle remains a negative control.

| Statement behavior | Case coverage |
| --- | --- |
| FULL-CG matches eager after state is produced or transferred | Mamba1 and Mamba2, an isolated final one-token chunk, mixed batches, real graph launches, eight subsequent output vectors per request. |
| Correct recurrent-state updates | Different prompt lengths and values, two simultaneous requests, four successive batches, and continued decoding after each transition. Full output distributions expose errors even if greedy argmax happens to stay unchanged. |
| Genuine first-token prompts | Fresh one-token prompts alone in a row and alongside long/stateful requests, including reuse after earlier requests finish. |
| Eager and ordinary decode remain intact | Dedicated eager case and all continuation steps, compared to unmodified Base eager serving. |
| Supported speculative behavior remains intact | Mamba2 with ngram proposals and accepted drafts; compare every returned token and distribution against unmodified Base with the same speculative configuration in eager mode. |

No reward condition names an Oracle helper or inspects metadata fields, buffer ownership, intermediate row ordering, or the location of the fix. Graph and accepted-draft observations establish that the intended workload ran; independently checked numeric outputs establish correctness. This is a behavioral benchmark, not a proof against arbitrary hostile rewrites of the Python runtime.

Mamba1 logprobs use an absolute tolerance of `4e-5`. Mamba2 uses `8e-3` with no relative tolerance: the frozen repository's `tests/kernels/mamba/test_mamba_ssm_ssd.py` permits `8e-3` absolute plus `5e-3` relative for float32 scan kernels. Calibration against trusted GPU eager serving measured errors of `0.0004301071` for FULL-CG and `0.0000715256` for speculative serving; generated tokens matched exactly. Dedicated Mamba1-only and Mamba2 state-address corruption controls check that this numerical allowance does not hide a missing Mamba2 repair.

A bounded Mamba1 cache holds two live requests plus the reserved block, forcing later requests to reuse state from completed requests. This exposed the old short-extends-only control returning wrong tokens for a fresh request; classifying a first token as decode is not rejected merely for its metadata representation. An isolated 17-token prompt with a 16-token scheduling budget also guarantees that the final one-token continuation is tested outside a larger mixed prefill batch. Distinct randomized prefixes prevent cache hits from skipping that transition.
