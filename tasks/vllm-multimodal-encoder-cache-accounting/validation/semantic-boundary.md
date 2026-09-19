# Encoder cache contract and verification boundary — 1.4.1

The task is a CPU-verifiable change to multimodal accounting, scheduling, cached payload storage and input selection. Its semantic boundary is processed media tokens/masks and encoder rows -> real request admission and scheduler rounds -> whole-item reservation -> real runner state/input preparation, batching, encoding and cache consumption -> main-model and lookahead embedding inputs -> completion, eviction and fresh admission.

The 1.4.0 statement adds one explicit requirement: with the encoder output fixed, increasing timestamp or other non-embedding prompt positions must not expand the cached embedding payload with the placeholder span. This is a contract expansion authorized during review. The historical dense-with-matching-profiling control was valid under 1.3.4 and is a negative under 1.4.0; its patch and historical results are preserved.

Version 1.4.1 leaves that statement unchanged. It closes a physical-eviction coverage gap and removes an allocation-API-dependent false rejection. Both changes enforce existing behavior without prescribing how candidate cache storage is organized.

## Real execution and substitutions

The verifier runs production `Request`, `Scheduler`, `GPUModelRunner`, `InputBatch`, registry, profiler and cache-manager constructors. It enters through `add_request`, `schedule`, `load_model`, `initialize_kv_cache`, `execute_model`, `propose_draft_token_ids`, `update_from_output` and `profile_run`. The runner itself calls its preparation, media batching, encoder and gather helpers. Scoring never calls those private helpers directly, fills a guessed encoder-cache layout or reads a named input tensor buffer.

A registered stateless neural model provides deterministic text embeddings and controlled encoder rows. Its ordinary `SupportsMultiModal.embed_input_ids` implementation performs the production embedding merge. The observer records inputs at the actual model forward boundary. Decoder arithmetic after that boundary is outside this contract: a controlled greedy output event is supplied to the real scheduler, in the model's observed request order. Draft arithmetic is likewise controlled, while the production runner chooses and gathers the shifted prompt window. This is a composed CPU execution test, not full pretrained-model generation or CUDA inference.

Single-rank Gloo groups are initialized normally. CUDA stream, event, allocation-device and pinning primitives are substituted with CPU equivalents, with shapes, values, state and ordering preserved. The controlled model has no learned parameter storage, so weight-load memory accounting is zero. Encoder payload and profiling storage are observed separately; `profile_run` and its input/encoder/dummy-forward path remain production code. No GPU timing, allocator peak or throughput claim is made.

## Fixture reachability

Media cases use the supported processed-input boundary: `MultiModalKwargsItem`, `MultiModalFeatureSpec`, `PlaceholderRange` and real requests. For masked media, `PromptUpdateDetails.select_token_id` derives the mask from an actual token sequence. Mask lengths, selected token positions and encoder row counts agree. Non-embedding positions contain ordinary text tokens; mask-free spans contain one encoder row per position. Empty and all-false cases follow the explicit statement. Requests have positive prompt length, sufficient context capacity, no prefix caching and a one-token generation budget. Admission and progress go through actual scheduler rounds; no computed-token counter is set by the fixture.

The external media factory is registered through the normal multimodal registry and supplies complete dummy processor results. Qwen3-VL analytical capacity tests use a real Qwen3-VL HF configuration and processing-info constructor. Actual image/video processors and the production resizing/temporal geometry calculate output rows. Controlled maximal resolution and frame limits yield the declared row counts; neither `get_num_video_tokens` nor `get_max_video_tokens` is replaced. Two-frame scored and four-frame independent cases distinguish analytical estimates from dummy-mask counting.

The decoder substitute has no attention layers. Empty decoder KV groups are supported by the runner and scheduler; encoder cache capacity is still real and bounded. Cache-pressure cases consume the complete encoder budget before a second request's text-only window, then exercise actual completion and eviction. This establishes the zero-resource state through supported scheduling transitions.

## Bidirectional map

| Statement behavior | Required observations |
|---|---|
| Count capacity, allocation and eviction in encoder rows | Public allocator exact-fit/one-short and insufficient-compute cases; real constructor budgets; repeated completed requests force turnover, with live encoder-derived storage observed throughout |
| Select current-window embeddings in order | Actual `execute_model` input values and positions for mixed sparse/dense/empty media and multiple requests |
| Preserve lookahead requirements | Actual scheduler lookahead plus `propose_draft_token_ids` delivering shifted inputs to the draft consumer |
| Empty windows progress without encoder work at zero resources | Another request first consumes all encoder capacity/budget; the cold text-only request still advances, without an encoder invocation |
| Reserve complete output on first use | Two items cannot jointly fit although the next window needs only one row; actual admission stops before the second item and later resumes |
| Reuse encoded items and retain correct request state | Multi-round real scheduling and model input preparation, request completion, batch removal and admission after draining |
| Preserve ordinary, all-false and empty behavior | Dense allocator cases, text-only and empty-media requests, zero-output planning floors |
| Planning/profile consistency | Dummy and Qwen3-VL analytical constructor consumers; actual profile execution versus retained runtime storage |
| Payload must not grow with non-embedding prompt positions | Fixed eight-row output across 16, 128 and 4096 prompt positions; live encoder-derived backing storage, including preallocated pools |
| Internal representation/interfaces remain free | Renamed helpers, renamed model/input buffers, constructor-initialized state, transposed and sparse payloads, equivalent mask allocation APIs, reusable backing storage, direct counting and alternative planning interfaces |

No test compares candidate patches with the Oracle. Workload payloads are fresh, and a parent-owned pure-Python reference checks the complete main and shifted input sequences. Batch order is matched by complete request input segments, not a prescribed persistent-batch row order. Case-count and authenticated-completion checks establish that required validation ran; they are not additional product features.

## Storage observation

The observer tracks weak C++ storage handles, aliases and mutations derived from the neural encoder's actual output. Strided and common sparse tensor layouts are supported; sparse values determine payload growth while index storage is included in profiling coverage. It does not inspect encoder-cache fields, tensor orientation or container layout. Masks and index metadata are not encoder payload. Decoder buffers that subsequently receive encoder values contribute a fixed amount across the compared workloads. The growth assertion allows bounded alignment overhead and does not require exact byte equality.

Constructor-time allocation is not exempt: a preallocated pool becomes observable when encoder data is copied into it. For profiling coverage, resident initialization storage and retained payload are counted as a union so existing decoder or encoder buffers are included in both paths without double counting. Shared backing allocations count once and weak handles do not extend their lifetime. The comparison observes physical CPU tensor backing storage; it is not a comprehensive accounting of arbitrary non-tensor encodings or an adversarial native-memory sandbox.

Torch factory operations that take an existing tensor only as a shape/dtype/device template do not inherit its value provenance. For example, a bool mask allocated with `output.new_empty` is treated like the same mask allocated with `torch.empty`. Subsequent actual copies or scatters of encoder values still mark their destination storage, including factory-created or preallocated buffers. This rule describes the operations' value semantics; it does not require a candidate allocation API, field name or payload dtype. Observer regression tests cover masks, template/like factories, aliasing and integer payloads.

The scored lifecycle workload uses one normally constructed scheduler/runner pair for 24 distinct 21-token requests, each containing an eight-row sparse media item that fills the encoder capacity. Every request is admitted, executed across chunks, checked at actual model inputs, completed and followed by the next request. Weak storage observations after completion compare residency after four warmup requests with later requests, permitting bounded allocation overhead. They do not require immediate release on completion or destruction of any particular Tensor. A correct implementation may retain a reusable pool. The payload-reuse positive control exercises that freedom; omitting retirement and retaining a copied payload outside the cache are separate negatives. The finite repeated workload detects the demonstrated accumulation bugs; it does not prove bounded memory for every possible allocation policy.

## Integrity and limits

The trusted parent compiles task-owned worker sources before dropping privileges. Workers cannot substitute a sibling module from the candidate directory. The native completion channel authenticates the original suite's completion; the parent checks all required stages and independently compares fresh observations. `SystemExit(0)`, `os._exit(0)`, startup hooks, copied observations, full stdout reports and direct completion callbacks remain negative controls. These checks address demonstrated bypasses, not arbitrary in-process or native-code tampering.

Positive controls also run independent declared geometries/windows and storage challenges. The published acceptance record must identify the frozen executable snapshot, actual rewards, intended failure reasons, stage timings and Harbor runs. Historical results are not relabeled as results for this version.
