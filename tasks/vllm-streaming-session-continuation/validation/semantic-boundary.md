# Review contract

Repeated scheduler new-request records for cached IDs -> real GPUModelRunner._update_states and InputBatch lifecycle -> consistent cache, unique batch rows, prompts, sampling/pooling state, block tables and refreshed M-RoPE metadata.

Runner state transitions, CachedRequestState, InputBatch add/remove/condense/refresh, sampling metadata and block tables execute for real. CPU tensors are sufficient: no GPU kernel, transfer or model forward determines this state transition. Scheduler records and last-PP-rank flag are valid deterministic producers; the M-RoPE model supplies deterministic positions while the production refresh method runs. Pooling uses real PoolingParams and state objects with a no-op pooler parameter-update producer. Additional cases remove one live row while retaining cached state before reinsertion, and finish then reuse an ID through the ordinary new-request path.

Six updates cover repeated/interleaved sessions, partial and zero output absorption, token->embedding->token switches, randomized IDs, seed/generator and prompt-logprob refresh; an explicit remove/reinsert case and finished-ID reuse are added, alongside three pooling updates and production M-RoPE refresh. Trusted parent compares raw cache and persistent-batch snapshots by values, never requiring cached-object identity. Independent challenge covers two-of-four absorption and a three-session interleave. Oracle rebuilds through the normal new-request path; alternative mutates CachedRequestState in place.

## Scoring integrity

The separate grading parent owns the current workload and keeps it in memory before candidate imports. Its read-only workload file provides actual matrix operands or continuation records to the unprivileged worker. Numerical references and expected state come from the parent's inputs, not input descriptions returned by the worker. The child still executes the real production paths described above. BMM launch and latency gates are unchanged.

The preserved observation-replay negative control executes no target checks and previously received reward 1. It is retained byte-for-byte in `validation/replay-observations.patch`. Current validation must reject it with reward 0, together with both Python early-success exits and attempted direct report writes. Additional scorer regressions replace input descriptions while retaining stale outputs, to distinguish behavioral checking from a freshness marker alone. Those are unit regressions and are reported separately from full Harbor trials.

For streaming, state snapshots copy values immediately so a correct in-place update cannot retrospectively mutate an earlier observation. Candidate state-object identity is not scored. Process isolation alone is not treated as evidence that target behavior ran; the recorded controls and behavioral assertions define the validated coverage.

## Evidence discipline

Old snapshots and direct Docker diagnostics are not final Harbor results. `e2e-evidence.json` records the actual image identity, executable hashes, raw run locations and final full-path outcomes.
