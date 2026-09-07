# Review and validation: persistent KV layout namespace (0.0.2)

Retain the task after hardening. The image and Oracle remain valid; the statement
and verifier now distinguish the intended legacy-portable contract from the
broader idea that every physically compatible runner combination must share.

## Contract and fixture corrections

The statement now says that existing portable V1 files remain readable after
the upgrade and across compatible parallel configurations. It also says V1 and
V2 need not share a namespace. This matches the upstream rollout fix without
requiring a candidate to infer a cache-schema migration policy.

All incompatible runner cases now enter through `build_offloading_config`.
The HND fixture supplies the block-stride indexing signal that the real backend
adds before config translation. Manual parallel variants start from the
candidate's translated V1 config and use `dataclasses.replace`, so additional
normalized fields survive and the verifier does not bind to the old
`OffloadingConfig` constructor.

## Behavioral coverage

The 19 scored cases cover two model identities, both V1/V2 migration directions,
same-runner restart hits, four varied V1/V2 layouts, TP/PP/PCP/DCP portable
sharing, layout-specific parallel misses, model isolation, and a verifier-created
pre-fix portable V1 artifact. Lookup, store, load, drain, shutdown, restart,
filesystem data and multiple keys remain behavioral checks.

A verifier-owned parent now requires one exact completion record from the real
filesystem lifecycle. It supervises the process session and kills the full group
on timeout. Verifier output is cleared before execution and JUnit must contain
the exact 19 expected test names with no failures, errors, skips, or duplicates.

## Alternatives, controls, and historical replay

The Oracle, filename-level layout suffix, runner cache-format, required
model-runner field, and physical-layout classifier all pass 19/19 and the
attested lifecycle. All five also pass an independent unseen FP32 model with
both runner directions, both same-runner restarts, TP=3 portable sharing, and
PP=3 layout-specific isolation; Base fails that challenge. Base, unconditional
fingerprinting, always-miss, distributed-only, public-model inclusion/exclusion,
and repository-conftest skip controls receive reward 0. Oracle plus
`SystemExit(0)` and `os._exit(0)` reaches 19/19 pytest but receives reward 0
because the parent sees no completion record.

All eight original patches were replayed unchanged. Attempts 1, 6, and 7 now
receive 19/19 and reward 1. Attempts 2–5 remain 18/19 because they invalidate
the now-explicit legacy portable namespace. Attempt 8 changes from 10/19 to
18/19 after the runner fixture correction and fails only the same legacy case.
Original 0.0.1 scores remain unchanged.

The final Harbor 0.22.0 matrix contains 14 cases, matches every expected reward,
and has zero exceptions. Raw results are retained under
`runs/persistent-kv-hardening-20260907-204000`.

## Limits and state

The CPU image executes the real config translation, filesystem tier, asynchronous
I/O, block files and cross-process restarts with deterministic aligned bytes. It
does not launch a physical GPU model runner. The HND layout signal is taken from
the production backend contract and the upstream incident trace.

Task version is 0.0.2. Changes are local and uncommitted. The image was not
rebuilt, and no push or PR was performed.
