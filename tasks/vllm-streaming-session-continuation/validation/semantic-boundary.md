# Semantic boundary

The instruction is byte-for-byte unchanged from task 2.0.0. Version 2.1.3 retains the public input adapter, multi-token streaming and text-output checks, and adds ordinary-generation coverage for the default cumulative output mode. The Oracle and environment remain unchanged. The documented native ABI cutoff approximation remains outside these verifier repairs.

Ordered public input chunks -> the existing asynchronous generation entrypoint -> real session, scheduler, runner, KV cache and sampling -> public output tokens and completion metadata -> input closure, cleanup and subsequent requests.

The worker uses one real A100 engine with ordinary default asynchronous scheduling and a small local GPT-2 model. All model computation and request transitions run for real. A separate trusted parent constructs fresh model weights and computes predictions with installed Transformers on CPU; it never imports candidate vLLM code. This is a correctness test of session state and outputs, not model quality or throughput.

## Public interface and representation freedom

The driver imports the existing `AsyncLLM` entrypoint. It does not import or look up a prescribed new chunk class. It uses the stream element type declared by the public `generate` annotation when available, or sends text values for raw-text/duck-typed interfaces. For a declared class, the adapter binds its public `prompt` parameter, or its sole required input when that field has another name. Keyword arguments preserve optional metadata defaults regardless of declaration order; positional-only parameters use the declared preceding defaults. Constructor binding does not execute candidate code, and errors from actual chunk construction propagate normally. The public-input rename, keyword-only input and raw-text-stream controls exercise different valid input representations. Internal scheduler helper names, queue types, batch buffers and placeholder representations are not inspected.

Input text has whitespace at chunk boundaries so concatenating text and concatenating the corresponding token sequences describe the same input. The saved tokenizer is reloaded and checked against the reference token IDs before any candidate runs. The EOS added token uses whole-word matching, so a vocabulary entry such as `w4` cannot split `w40`.

The statement does not specify how much generated output becomes the next prompt. The reference therefore accepts predictions for every ordered generated-token prefix, including retaining all generated tokens. It still requires all accepted input chunks to remain in order and every returned token to match an independently computed valid continuation. A correct alternative that retains all generated output is required to pass.

Multi-chunk streaming workloads use an ample budget and explicit stop conditions. The multi-token continuation starts with at least three generated tokens; every allowed retained-context prefix stops each segment within six tokens and finishes the whole two-chunk workload before the budget could bind. Burst and delayed input use identical prompts and sampling parameters. A separate single-chunk stream produces four tokens with EOS ignored and no stop tokens, which exercises the ordinary generation budget without choosing per-segment versus per-session semantics. The metadata-refresh case still transitions from an explicit stop token to EOS under the same sampling parameters.

The worker records public text as well as token IDs. The trusted reference removes explicit stop tokens from the text when the public sampling option excludes them, lets the saved tokenizer handle special tokens, and decodes the visible output with its prompt prefix. DELTA scoring compares concatenated text and token sequences, without prescribing output frame sizes. Multi-token cases exercise both stop-token exclusion and inclusion. Ordinary reference output must contain visible text so an implementation returning empty text cannot pass by coincidence. Completion metadata must match one consistent allowed continuation path.

Ordinary requests run before and after streaming in both explicit DELTA mode and the existing default CUMULATIVE mode. The cumulative cases omit `output_kind` when constructing `SamplingParams`. All four ordinary cases generate eight tokens with EOS ignored and no explicit stops. DELTA frames append new content; cumulative frames replace the previous snapshot and must preserve its token and text prefixes. The final sequence and text match the independent reference and the corresponding DELTA request. A single coalesced cumulative frame is valid; no minimum frame count, fixed frame size, or timing threshold is scored.

Input closure may be represented by normal generator exhaustion or a final public output. The test does not require a last `finished=True` frame or a private end sentinel. Delayed input waits for actual segment completion before providing the next chunk or closing; fixed sleeps are not used to infer lifecycle state.

## Bidirectional coverage

| Existing statement requirement or direct public contract | Scored behavior |
|---|---|
| Ordered chunks continue one session without missing or duplicated tokens | Single- and multi-token streams, including burst and delayed continuations, must match complete independent predictions |
| Preserve valid context while applying new input | The workload is selected to distinguish preserved history from independently processing only the latest chunk; accepted generated-context prefixes are enumerated independently |
| Per-segment state remains consistent; prior state must not stay active | Public stop reason must match the actual termination condition, including explicit stop followed by EOS; both queued and delayed continuations run |
| Interleaved sessions do not affect one another | Both concurrent sessions match their independent predictions and their separate executions |
| Burst and delayed arrivals work | The same chunks run both immediately and with the next chunk waiting on observed completion |
| Closing after one or more chunks works | One-chunk, multi-chunk, and close-after-output sessions terminate and return the predicted outputs |
| Reuse an ended request ID | Reused-ID output matches a fresh session with the same input |
| Ordinary non-streaming behavior is unchanged | DELTA and default CUMULATIVE token IDs, public text and completion metadata are compared before and after streaming; cumulative snapshots preserve prior prefixes |
| Public generated output is preserved | Concatenated output text follows the saved tokenizer and stop-token visibility options; a coalesced-output correct control exercises different frame sizes |
| Keep using the v1 generation lifecycle | The end-to-end driver exercises the existing engine, scheduler, runner, sampling and output paths; it supplies no scheduler records or synthetic state transitions |

Public completion metadata is an existing output contract: an EOS completion has no explicit stop-token reason. Candidate-private fields are not used to establish this property.

## Reference implementation and controls

The reference now snapshots the completed segment's stop reason before applying a queued continuation and clears the next segment's old reason. It also resolves a resumable segment's pending sample before dispatching another decode step, preventing late results from an early-stopped segment contaminating its continuation. This per-session scheduling choice is not required by the tests; ordinary requests retain existing scheduling behavior, and no throughput target is scored.

All validation patches apply directly to Base, as required by the repository's `prepare-case` entrypoint. Correct controls rename the public input type, put an optional field before a keyword-only prompt, use raw text streams, retain all generated context, and combine output frames within each segment. The coalescing control appends DELTA content and replaces CUMULATIVE content, copying buffered outputs so aggregation cannot mutate the engine's live token lists. Its former implementation, which appended cumulative prefixes, is retained as `cumulative-output-duplication.patch` with expected reward 0. Negative controls also cap every streaming segment at one token or clear all public text while retaining correct token IDs. The forged-report control includes the current text field and must fail behavioral comparison rather than a missing-field error. `validation/test_input_adapter.py` checks constructor forms and defaults without vLLM or GPU dependencies; `validation/test_reference_workloads.py` checks multi-token and output-mode fixture properties and retryable unsuitable weights. These are verifier-development tests, not extra candidate requirements.

## Scoring and limits

The scorer requires complete public results and compares them with independently calculated predictions from fresh weights. Request IDs and model weights vary on each run. Reference answers remain in a root-only directory; the worker can read the model and requested inputs, but not the answer files. Near-tied greedy fixtures and weights that cannot produce a discriminating workload are regenerated before candidate execution. The report records how many reference attempts were needed; candidate failures are not retried by this mechanism.

A well-formed report or a zero exit code is insufficient. The forged-report control is kept compatible with the current result format and must fail the token comparison, rather than schema validation. These protections reject the demonstrated report-only and constant-output bypasses; they are not a proof against an arbitrary candidate implementing an entire substitute computation or tampering with every Python observation point.

The existing image and native ABI bridge are unchanged. The v0.15.1 native donor is still the approximation documented in the environment lock; real execution and independent predictions validate the exercised behavior, but this revision does not claim that those binaries were built from the frozen Base source.
