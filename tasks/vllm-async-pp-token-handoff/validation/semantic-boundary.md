# Async PP behavioral boundary

Version 1.4.0 targets single-node mp execution, PP=2, ordinary single-token decoding, chunked prefill, request completion and batch changes. external_launcher, speculative decoding, V2 runner, distributed KV offload and preemption are not added by this revision. This revision repairs the verifier's Worker/executor boundary; the task statement and candidate requirements are unchanged.

Request admission -> production scheduler rounds -> mp executor and workers -> production runner, attention, KV cache and sampling -> GPU token handoff -> subsequent model inputs -> output collection and request completion.

## Two complementary test boundaries

The component behavior suite admits real Request objects through the scheduler selected by the candidate's configuration. Every runner execution receives the complete object returned by that scheduler's schedule() method, including candidate-added metadata. Initial cached states and generated history are created through real execute, sample and collection cycles; they are not populated by the fixture. Both PP ranks advance through real executor/Worker transitions. Controlled logits make the expected samples deterministic; the tiny model forward still runs. GPU scenarios reuse an engine and initialized groups with fresh requests. CPU configuration and scheduler cases similarly share one process. A failing or hung suite cannot pass, and separate candidate implementations still run in separate containers.

The GPU behavior driver creates a real local LLM engine with the candidate-selected scheduler and mp executor. Real Worker construction, device initialization, model loading, KV setup, activation transfer and execute/sample dispatch run in their normal processes. Requests enter the actual scheduler; its complete outputs are submitted through the executor, and actual returned outputs are collected through the scheduler. The driver never fabricates SchedulerOutput or initializes a runner by hand. This lets implementations add scheduler metadata or place token receipt in Worker without being bypassed.

Task-owned Worker probes wrap the existing execute/sample calls and the actual model forward. They choose valid logits and capture the model's input arguments by request identity; model execution and candidate transport still run normally. The async engine and initialized groups are reused across scenarios, with requests completed or aborted between cases. The synchronous check constructs a separate real mp engine. This is a subsystem behavior test through executor and Worker, while the separate ordinary LLM generation suite checks the full engine loop.

The mp E2E suite uses a small locally generated OPT model with real weights, attention, KV cache, sampling, executor worker processes, scheduling and output collection. An independent root-owned Transformers execution computes expected greedy token sequences from the same weights and prompts. Candidate configurations cover async/sync crossed with PP=1/2. Each engine handles mixed prompt lengths and generation budgets, finishes the workload, and then serves a fresh request. In the async PP=2 case, a task-owned RPC gate temporarily holds the existing worker loops. Real request execution must submit a later step for the same request before the gate releases earlier work. This observes the public mp executor submission boundary without inspecting future queues, helper names or placeholder storage. The frontend runs in-process for this case, while both model workers remain real mp processes. The gate bounds a causal liveness condition; these are correctness tests, not model-quality or throughput benchmarks.

## Bidirectional coverage

| Task requirement or direct implication | Scored behavior |
|---|---|
| Single-node mp, PP=2, async scheduling | CPU configuration check and real async PP=2 mp generation |
| More than one step per request in flight with sufficient budget/capacity | Scheduler reentry plus a real mp output gate: the same request must submit another model step before held worker work is released; repeated scheduling/output accounting |
| Sampled tokens reach the next decode step through GPUs | Candidate-owned PP ranks communicate; an independent observer supplies GPU sampler inputs and compares next-input GPU payloads |
| No CPU-object handoff, blocking D2H or host wait | CPU-object checks during sampling, with CUDA flow/runtime observation across Worker execute/sample; activation metadata and task-side CPU inspection are outside the sampled-token restriction |
| Normal CPU output collection remains allowed | Actual returned sampler outputs and complete engine outputs are collected and compared after handoff |
| Requests stay associated with ordered tokens after removal/reordering | BASIC, REORDERED and INTEGRATED scenarios compare actual subsequent inputs |
| Remaining prompt survives batch compaction | COMPACTION removes the leading request while a long prompt is unfinished, then executes full preparation of its remaining prompt |
| Mixed chunked prefill and decode | COMPACTION and real-model E2E workloads |
| All unfinished prefill chunks progress without discarded-result dependency | PREFILL_PROGRESS holds last-stage logits until the earlier stage actually consumes its next GPU input; skipping discarded sampling entirely is also allowed |
| Idle/no-output final stage does not receive tokens | IDLE uses a real empty executor step; as in EngineCore, zero scheduled tokens do not dispatch sample_tokens |
| Multi-round scheduling/output collection through completion, no missing/duplicate outputs | Scheduler closure plus real-model E2E exact sequences and lengths |
| Pending work does not strand runnable requests | Scheduler reentry, bounded closure, and new admission after draining |
| Do not break synchronous scheduling or PP=1 | Scheduler matrix, synchronous next-input case, and real-model async/sync × PP=1/2 matrix |

Tests do not add performance targets, force a particular sentinel, require a candidate-added helper, or assert Oracle map contents. Timeouts bound hangs rather than benchmark throughput. The fresh-request check follows from preserving scheduling after completion; PP=1 and synchronous cases follow directly from the final sentence of the task. Model/fixture sanity and supervisor integrity checks establish valid evaluation execution rather than additional candidate features.

## Transport freedom and trust boundary

Both ends of the production PP handoff load the candidate implementation. The root-owned observer does not stand in for either PP endpoint. Its separate observation groups provide sampler inputs and receive actual downstream GPU inputs. Fixed shapes on these observation groups describe task-owned sampler/model boundaries, not the candidate's wire protocol. Production broadcast, P2P, wire dtype/layout and storage representation are not prescribed by the observer. A P2P alternative that also renames internal input-preparation and sampling helpers, plus a reversed-storage alternative, exercise this distinction. Model inputs are captured at the model forward argument and compared by request identity; the comparison does not read a prescribed runner input buffer. Subsequent events come from the candidate's real scheduler, driven by task-owned requests and real collected outputs, rather than a hand-written subset of scheduler fields.

A complete worker report is necessary but insufficient: the supervisor also requires the independent GPU comparison. This closes the demonstrated import-time report-only bypass. It does not make arbitrary Python worker instrumentation tamper-proof, and the E2E output adapter also executes in a candidate-containing process. Do not describe this as comprehensive malicious-code resistance. Behavior tests use the frozen scheduler/executor and Worker dispatch interfaces, while E2E runs through the ordinary LLM API. The driver process identity in supervisor framing is distinct from the two PP worker identities.

CUDA events recorded before a model forward may guard ordinary input-buffer reuse. Their records cannot depend on samples from that forward. The observer carries this provenance across execute/sample calls and permits a prior-event wait only until the event is recorded again; newly recorded events and implicit CUDA runtime waits remain checked. Events from a completed empty round can also precede the next request without depending on new samples; waits within the empty round are still observed. This distinction uses event provenance rather than a required runner attribute name.

Root reference outputs and partial E2E comparison results are written with mode 0600 before any answer bytes are exposed. Candidate scratch outputs are removed after each engine process group exits. A copied-reference negative control checks this boundary; the corrected forged-report control must supply a valid suite report so that rejection demonstrates the independent comparison rather than a formatting error.

## Historical motivation and evidence status

The scoped regressions derive from upstream fixes for all-prefill broadcast stalls (38726), prompt loss during compaction (41133), and last-rank receive on empty execution (40749). Tests assert consequences rather than patch shapes. The external-launcher fix (33701) and later speculative-decoding repairs are outside this contract.

The frozen worker-boundary-final source passes both original Astra replays, all 19 active Base/Oracle/control cases, and Harbor Oracle. Final hashes and runtime evidence are recorded in e2e-evidence.json. Earlier runner-only and intermediate Worker results are historical evidence and do not certify this revision.

## Control interpretation

The patch labels identify curator controls, not additional task requirements. Each expected reward follows from the behavior below; a mismatch must be investigated rather than repaired by changing the expected reward.

| Control | Contract consequence | Expected reward |
|---|---|---|
| Base | Async PP=2 is not supported at the requested boundary | 0 |
| Oracle | Supports the stated lifecycle, GPU handoff and preserved modes | 1 |
| Reversed storage alternative | Changes token storage and placeholder representation while preserving subsequent inputs and outputs | 1 |
| P2P alternative | Changes the PP transfer mechanism and renames internal helpers while preserving subsequent inputs and outputs | 1 |
| Activation metadata alternative | Uses equivalent CPU object APIs for activation metadata while sampled tokens remain on GPU | 1 |
| Worker-owned transport alternative | Uses the other unchanged Astra production implementation, placing token receipt after activation forwarding in Worker | 1 |
| Worker handoff host wait | Adds a stream synchronization after Worker receives tokens | 0 |
| Scheduler metadata alternative | Uses the production changes from the Astra submission, carrying sampling positions through the real scheduler output and retaining token history by request and position | 1 |
| Historical Oracle | Retains scoped prefill/compaction/idle defects | 0 |
| Implicit CUDA synchronization | Waits for GPU work through a runtime operation during handoff | 0 |
| Last-stage receive | Makes the final Worker enter token receipt during a reachable empty execution | 0 |
| All-prefill broadcast wait | Prevents earlier stages advancing while discarded samples are unavailable | 0 |
| Compaction token loss | Corrupts the unfinished prompt after another request is removed | 0 |
| Duplicate collected token | Returns generated output more than once | 0 |
| Serial executor | Waits for earlier work before submitting another eligible request step | 0 |
| Forged success report | Reports success without performing required GPU behavior | 0 |
| Successful SystemExit | Exits before required checks complete | 0 |
| Successful os._exit | Exits immediately before required checks complete | 0 |
| Copied E2E reference | Substitutes a copied answer for required model execution | 0 |

The historical last-rank sample guard is not directly reverted in the current control: EngineCore does not call sample_tokens after an empty step in this scope. The control instead inserts the wrong receive in the actual empty Worker execution, testing the stated role/liveness invariant without inventing an extra sampling call. CPU activation metadata is also allowed to use equivalent object APIs; a separate correct alternative protects this boundary from an overbroad communication ban.
