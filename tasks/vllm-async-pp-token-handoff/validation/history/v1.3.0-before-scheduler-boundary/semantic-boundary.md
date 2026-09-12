# Async PP behavioral boundary

Version 1.3.0 targets single-node mp execution, PP=2, ordinary single-token decoding, chunked prefill, request completion and batch changes. external_launcher, speculative decoding, V2 runner, distributed KV offload and preemption are not added by this revision.

Request admission -> production scheduler rounds -> mp executor and workers -> production runner, attention, KV cache and sampling -> GPU token handoff -> subsequent model inputs -> output collection and request completion.

## Two complementary test boundaries

The component behavior suite uses real scheduler and runner constructors, request transitions, buffers, execute/sample paths, NCCL groups and input preparation. Only model arithmetic is replaced with controlled sampler inputs. Seven GPU scenarios reuse one pair of processes and initialized groups; each constructs fresh runner/request state. CPU configuration and scheduler cases similarly share one process. A failing or hung suite cannot pass, and separate candidate implementations still run in separate containers.

The mp E2E suite uses a small locally generated OPT model with real weights, attention, KV cache, sampling, executor worker processes, scheduling and output collection. An independent root-owned Transformers execution computes expected greedy token sequences from the same weights and prompts. Candidate configurations cover async/sync crossed with PP=1/2. Each engine handles mixed prompt lengths and generation budgets, finishes the workload, and then serves a fresh request. In the async PP=2 case, a task-owned RPC gate temporarily holds the existing worker loops. Real request execution must submit a later step for the same request before the gate releases earlier work. This observes the public mp executor submission boundary without inspecting future queues, helper names or placeholder storage. The frontend runs in-process for this case, while both model workers remain real mp processes. The gate bounds a causal liveness condition; these are correctness tests, not model-quality or throughput benchmarks.

## Bidirectional coverage

| Task requirement or direct implication | Scored behavior |
|---|---|
| Single-node mp, PP=2, async scheduling | CPU configuration check and real async PP=2 mp generation |
| More than one step per request in flight with sufficient budget/capacity | Scheduler reentry plus a real mp output gate: the same request must submit another model step before held worker work is released; repeated scheduling/output accounting |
| Sampled tokens reach the next decode step through GPUs | Candidate-owned PP ranks communicate; an independent observer supplies GPU sampler inputs and compares next-input GPU payloads |
| No CPU-object handoff, blocking D2H or host wait | Object-collective interception and CUDA flow/runtime observation during sampling and next-input consumption; test-side CPU inspection is outside observation |
| Normal CPU output collection remains allowed | Actual returned sampler outputs and complete engine outputs are collected and compared after handoff |
| Requests stay associated with ordered tokens after removal/reordering | BASIC, REORDERED and INTEGRATED scenarios compare actual subsequent inputs |
| Remaining prompt survives batch compaction | COMPACTION removes the leading request while a long prompt is unfinished, then executes full preparation of its remaining prompt |
| Mixed chunked prefill and decode | COMPACTION and real-model E2E workloads |
| All unfinished prefill chunks progress without discarded-result dependency | PREFILL_PROGRESS releases last-stage sampling only after the earlier stage prepares its next chunk |
| Idle/no-output final stage does not receive tokens | IDLE uses a real empty execute followed by the split sample phase |
| Multi-round scheduling/output collection through completion, no missing/duplicate outputs | Scheduler closure plus real-model E2E exact sequences and lengths |
| Pending work does not strand runnable requests | Scheduler reentry, bounded closure, and new admission after draining |
| Do not break synchronous scheduling or PP=1 | Scheduler matrix, synchronous next-input case, and real-model async/sync × PP=1/2 matrix |

Tests do not add performance targets, force a particular sentinel, require a candidate-added helper, or assert Oracle map contents. Timeouts bound hangs rather than benchmark throughput. The fresh-request check follows from preserving scheduling after completion; PP=1 and synchronous cases follow directly from the final sentence of the task. Model/fixture sanity and supervisor integrity checks establish valid evaluation execution rather than additional candidate features.

## Transport freedom and trust boundary

Both ends of the production PP handoff now load the candidate implementation. The root-owned observer does not stand in for either PP endpoint. Its separate observation groups provide sampler inputs and receive actual downstream GPU inputs. Fixed shapes on these observation groups describe task-owned sampler/model boundaries, not the candidate's wire protocol. Production broadcast, P2P, wire dtype/layout and storage representation are not prescribed by the observer. A P2P alternative that also renames internal input-preparation and sampling helpers, plus a reversed-storage alternative, exercise this distinction. Model inputs are captured at the model forward argument and compared by request identity; the comparison does not read a prescribed runner input buffer. Subsequent scheduler events come from independent workload facts, not placeholder lengths.

A complete worker report is necessary but insufficient: the supervisor also requires the independent GPU comparison. This closes the demonstrated import-time report-only bypass. It does not make arbitrary Python worker instrumentation tamper-proof, and the E2E output adapter also executes in a candidate-containing process. Do not describe this as comprehensive malicious-code resistance. Component tests retain the frozen scheduler/runner interfaces, while E2E runs through the ordinary LLM API.

CUDA events recorded before sampling may guard ordinary input-buffer reuse. The observer permits waits on those prior events only until they are recorded again; newly recorded events and implicit CUDA runtime waits remain checked. This distinction uses event provenance rather than a required runner attribute name.

Root reference outputs and partial E2E comparison results are written with mode 0600 before any answer bytes are exposed. Candidate scratch outputs are removed after each engine process group exits. A copied-reference negative control checks this boundary; the corrected forged-report control must supply a valid suite report so that rejection demonstrates the independent comparison rather than a formatting error.

## Historical motivation and evidence status

The scoped regressions derive from upstream fixes for all-prefill broadcast stalls (38726), prompt loss during compaction (41133), and last-rank receive on empty execution (40749). Tests assert consequences rather than patch shapes. The external-launcher fix (33701) and later speculative-decoding repairs are outside this contract.

Final executable hashes, stability, negative controls and Harbor results must be recorded after the optimized verifier is frozen. Earlier nine-stage results are supporting evidence only and do not certify the optimized verifier.

## Control interpretation

The patch labels identify curator controls, not additional task requirements. Each expected reward follows from the behavior below; a mismatch must be investigated rather than repaired by changing the expected reward.

| Control | Contract consequence | Expected reward |
|---|---|---|
| Base | Async PP=2 is not supported at the requested boundary | 0 |
| Oracle | Supports the stated lifecycle, GPU handoff and preserved modes | 1 |
| Reversed storage alternative | Changes token storage and placeholder representation while preserving subsequent inputs and outputs | 1 |
| P2P alternative | Changes the PP transfer mechanism and renames internal helpers while preserving subsequent inputs and outputs | 1 |
| Historical Oracle | Retains scoped prefill/compaction/idle defects | 0 |
| Implicit CUDA synchronization | Waits for GPU work through a runtime operation during handoff | 0 |
| Last-stage receive | Enters a receive path on the final stage after empty execution | 0 |
| All-prefill broadcast wait | Prevents earlier stages advancing while discarded samples are unavailable | 0 |
| Compaction token loss | Corrupts the unfinished prompt after another request is removed | 0 |
| Duplicate collected token | Returns generated output more than once | 0 |
| Serial executor | Waits for earlier work before submitting another eligible request step | 0 |
| Forged success report | Reports success without performing required GPU behavior | 0 |
| Successful SystemExit | Exits before required checks complete | 0 |
| Successful os._exit | Exits immediately before required checks complete | 0 |
| Copied E2E reference | Substitutes a copied answer for required model execution | 0 |
