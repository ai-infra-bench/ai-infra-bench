# Semantic boundary

The instruction is byte-for-byte unchanged from task 2.0.0. This revision changes the verifier and reference implementation, without adding a required chunk class, a generated-token retention algorithm, or per-segment budget overrides to the task.

Ordered public input chunks -> the existing asynchronous generation entrypoint -> real session, scheduler, runner, KV cache and sampling -> public output tokens and completion metadata -> input closure, cleanup and subsequent requests.

The worker uses one real A100 engine with ordinary default asynchronous scheduling and a small local GPT-2 model. All model computation and request transitions run for real. A separate trusted parent constructs fresh model weights and computes predictions with installed Transformers on CPU; it never imports candidate vLLM code. This is a correctness test of session state and outputs, not model quality or throughput.

## Public interface and representation freedom

The driver imports the existing `AsyncLLM` entrypoint. It does not import or look up a prescribed new chunk class. It uses the stream element type declared by the public `generate` annotation when available, or sends text values for raw-text/duck-typed interfaces. The public-input rename and raw-text-stream controls exercise different valid input representations. Internal scheduler helper names, queue types, batch buffers and placeholder representations are not inspected.

Input text has whitespace at chunk boundaries so concatenating text and concatenating the corresponding token sequences describe the same input. The saved tokenizer is reloaded and checked against the reference token IDs before any candidate runs. The EOS added token uses whole-word matching, so a vocabulary entry such as `w4` cannot split `w40`.

The statement does not specify how much generated output becomes the next prompt. The reference therefore accepts predictions for every ordered generated-token prefix, including retaining all generated tokens. It still requires all accepted input chunks to remain in order and every returned token to match an independently computed valid continuation. A correct alternative that retains all generated output is required to pass.

Streaming workloads use a non-binding budget and explicit stop conditions. The metadata-refresh case transitions from an explicit stop token to EOS under the same sampling parameters. No assertion chooses whether a changed `max_tokens` would apply per segment or per session. Ordinary requests retain their existing, unambiguous single-request budget behavior.

Input closure may be represented by normal generator exhaustion or a final public output. The test does not require a last `finished=True` frame or a private end sentinel. Delayed input waits for actual segment completion before providing the next chunk or closing; fixed sleeps are not used to infer lifecycle state.

## Bidirectional coverage

| Existing statement requirement or direct public contract | Scored behavior |
|---|---|
| Ordered chunks continue one session without missing or duplicated tokens | Burst and delayed streams must match independent continuation predictions; counts follow the configured stop conditions |
| Preserve valid context while applying new input | The workload is selected to distinguish preserved history from independently processing only the latest chunk; accepted generated-context prefixes are enumerated independently |
| Per-segment state remains consistent; prior state must not stay active | Public stop reason must match the actual termination condition, including explicit stop followed by EOS; both queued and delayed continuations run |
| Interleaved sessions do not affect one another | Both concurrent sessions match their independent predictions and their separate executions |
| Burst and delayed arrivals work | The same chunks run both immediately and with the next chunk waiting on observed completion |
| Closing after one or more chunks works | One-chunk, multi-chunk, and close-after-output sessions terminate and return the predicted outputs |
| Reuse an ended request ID | Reused-ID output matches a fresh session with the same input |
| Ordinary non-streaming behavior is unchanged | Normal prompt requests run before and after the streaming workload and match independent predictions |
| Keep using the v1 generation lifecycle | The end-to-end driver exercises the existing engine, scheduler, runner, sampling and output paths; it supplies no scheduler records or synthetic state transitions |

Public completion metadata is an existing output contract: an EOS completion has no explicit stop-token reason. Candidate-private fields are not used to establish this property.

## Reference implementation and controls

The reference now snapshots the completed segment's stop reason before applying a queued continuation and clears the next segment's old reason. It also resolves a resumable segment's pending sample before dispatching another decode step, preventing late results from an early-stopped segment contaminating its continuation. This per-session scheduling choice is not required by the tests; ordinary requests retain existing scheduling behavior, and no throughput target is scored.

All validation patches apply directly to Base, as required by the repository's `prepare-case` entrypoint. Correct controls rename the public input type, use raw text streams, and retain all generated context. Negative controls drop later chunks, break ordinary generation, preserve stale stop metadata, allow old in-flight outputs, return constants, forge a complete correctly shaped report, or exit before checks execute.

## Scoring and limits

The scorer requires complete public results and compares them with independently calculated predictions from fresh weights. Request IDs and model weights vary on each run. Reference answers remain in a root-only directory; the worker can read the model and requested inputs, but not the answer files. Near-tied greedy fixtures are regenerated before candidate execution to avoid rejecting correct numerical implementations due to rounding.

A well-formed report or a zero exit code is insufficient. The forged-report control is kept compatible with the current result format and must fail the token comparison, rather than schema validation. These protections reject the demonstrated report-only and constant-output bypasses; they are not a proof against an arbitrary candidate implementing an entire substitute computation or tampering with every Python observation point.

The existing image and native ABI bridge are unchanged. The v0.15.1 native donor is still the approximation documented in the environment lock; real execution and independent predictions validate the exercised behavior, but this revision does not claim that those binaries were built from the frozen Base source.
