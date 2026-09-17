# Behavior and verification boundary

Environment override and local HF metadata -> real ModelConfig and VllmConfig -> Worker construction and init_device -> actual V1/V2 runner instance, or startup failure with a diagnostic.

This is a runner-selection task. Weight loading and text generation do not determine which runner is instantiated. The verifier uses local model metadata, real CUDA/NCCL initialization and real runner constructors. Only Elastic EP orchestration is replaced. The image includes normal upstream sources and native components, but no task-specific helpers or fixtures during the agent phase.

| Statement requirement | Observable check | Cases |
| --- | --- | --- |
| Supported dense, unquantized Qwen3 generation defaults to V2 | Startup creates V2 | auto_qwen3, auto_repeat |
| Other automatic configurations stay on V1 | Startup creates V1 | Qwen2, pooling (including MEAN), FP8, MoE |
| Unsupported Qwen3 options do not activate V2 automatically | Startup creates V1 | KV sharing, explicit logits processor, prompt embeddings, raw/processed logits |
| Explicit 0 forces V1 | Startup creates V1 | Plain Qwen3, KV sharing, raw logits, MEAN pooling |
| Explicit 1 requests compatible V2 outside the automatic rollout | Startup creates V2 | Qwen3, Qwen2, normalized LAST decoder embeddings |
| Incompatible forced V2 fails startup clearly | No successfully initialized runner, plus a nonempty diagnostic | KV sharing, logits processor, prompt embeddings, raw/processed logits, MEAN/CLS pooling and unnormalized LAST embeddings |
| Worker consumes the selected runner | Inspect real constructed model_runner | Every successful startup; wrong-constructor control |

These options are representative applications of the statement's compatibility requirement, rather than an exhaustive list of every configuration supported by vLLM. No test requires a particular environment-accessor representation, private worker field, helper name, exception type, error keyword, or validation phase before startup finishes. Each environment override gets a separate process, so import-time override caching remains valid. Repeated cases within a group use fresh configurations and workers with distributed cleanup.

The negative startup checks automatically require a diagnostic but cannot assess the full quality of an explanation. Reference diagnostics are also inspected in the validation logs. The tests do not establish compatibility for every speculative, distributed or platform configuration, nor do they certify scheduler migration or generation correctness.

The supervisor independently verifies CUDA availability, authenticates case order/completion and owns reward.txt. Candidate stdout is never completion evidence. The native checkpoint accepts calls from the preloaded suite code object only. Report forgery, direct callback invocation and early exits have separate negative controls. This is not isolation against arbitrary native-memory access or arbitrary mutation of the in-process Python suite.

The six pooling cases use public ModelConfig/PoolerConfig options available at Base. V2 currently selects last-token states and always normalizes them; forcing MEAN, CLS or disabled normalization must reject at startup. Compatible normalized LAST is a paired positive, and MEAN under auto and forced V1 preserves fallback behavior. These cases add coverage of an existing requirement, not V2 pooling features.
