# PR84 flash rollout review — completed campaign

Final conclusion: retain the task with the repaired 1.3.3 verifier. Two A100
Harbor batches of four attempts and complete trajectory review are finished. All four original rewards remain 0 after complete saved
repository regrading. One original assertion rejected a valid internal API
refactor, but that answer also independently violates video capacity accounting;
it is not a demonstrated incorrect final reward. A previously accepted dense
cache control underprofiles its live storage and is now correctly rejected.
The second frozen four-attempt batch also scored 0/4; independent replay
confirms a real video-capacity defect in all four, with no newly demonstrated
false reward or justified verifier change. Stop here on evidence, not pass rate.

## Scope and provenance

Oracle-based validation. The user authorized iterative A100 Harbor batches of
four `deepseek-v4-flash[1m]` attempts and verifier repairs. Model settings came
from `/data/akg_kernel_bench_lite/kernelgen/env.sh`; immutable provider revision
was not supplied. Reasoning effort remained the CLI/provider default. Harbor
0.22.0 used curator `OfflineClaude` with native Claude Code 2.1.238. Every trial
had 4 CPUs / 16 GiB and `/workspace/vllm`; only the model endpoint was allowed
for agent egress and grading was offline. These are CPU behavioral lifecycle
checks executed in Docker on A100, not GPU inference or CUDA memory benchmarks.

Base: `676db55eecf8b6d9ec38ea243cf6f35ea8378ec6`.
Oracle: `f5f51e5931ffd99afe69696b60765b88d3eb13f2`.
Image: `sha256:8d200d6c23d542fb41b456cb55bf5c984b1c467c2020e31fb0e053e120c5f852`.
Original batch: source `753a301`, task 1.3.0, A100
`/tmp/pr84-flash-round-01`, no retries, concurrency 4.
Repaired executable: `d85f6ad`, task 1.3.3. The instruction and image did not
change between these versions. Frozen Harbor task.toml appends the trusted
after-agent collector command; the control matrix uses that same frozen
configuration. Its hash differs from repository task.toml only for this appended
collection step, while all scored test files match the executable revision. Hash identities are preserved in
[evidence](evidence/rollout-hardening-1.3.3/).

The repository rollout review skill and its differential-cases/reporting
references were read. The local review ledger records skill hashes and every
reviewed observable trajectory chunk. All eight complete observable trajectories,
including tool inputs/results and final responses, were reviewed. Round 01 8z
had two Explore subagents; round 02 7z had one Explore and DNe one general-purpose
review subagent. Their observable activity was included. Internal private reasoning is not treated as
observable action evidence. Exact duplicate source outputs were indexed once
with source/hash references. Original logs and scores were not rewritten.

Each attempt has an after-agent, before-verifier manifest, tracked binary diff,
untracked archive, full repository archive, status and HEAD. All artifact and
full-tree file hashes match, collection is complete, no reward existed yet,
and no unsupported file type was reported. Every final tracked diff and all
eight untracked Python files across both batches were inspected (four in each
batch; AY delivered no untracked files). Capture excludes only .git and
hash-identical native overlays, restored from the pinned image for replay.

Round 01 containers were unexpectedly removed by Harbor: `delete=False` alone
was insufficient. Full outside-repository state cannot be replayed. Complete
observable commands show temporary test scripts and normal CLI files, failed
package downloads, and no successful package install or outside-repository
runtime modification. Exact repository replay is supported; whole-container
replay is not. `keep_containers=True` was added and actual Harbor canary 04
proved retention before the second paid batch.

## Original four attempts

ATIF Agent Step counts only `source=agent`; total steps includes other sources.
Tool calls sum the ATIF tool-call arrays, not shell command count. Native
subagent activity was reviewed separately. File/line counts describe the final
capture, not cumulative edit operations. Times are seconds from Harbor.

| Trial | Original reward | 1.3.3 replay | Agent/total steps | ATIF tools | Tracked files + untracked | Tracked +/− lines | Total / agent / verifier seconds |
|---|---:|---:|---:|---:|---:|---:|---|
| task__8zM6rpm | 0 | 0 | 247/250 | 339 | 11+1 | +533/−104 | 1268.097 / 1226.779 / 13.863 |
| task__Ks4PMLs | 0 | 0 | 176/177 | 186 | 10+1 | +321/−61 | 1358.815 / 1318.710 / 12.966 |
| task__RfY7UMz | 0 | 0 | 168/169 | 185 | 10+1 | +525/−66 | 1129.975 / 1089.186 / 13.653 |
| task__tBcBwC7 | 0 | 0 | 138/139 | 160 | 10+1 | +457/−81 | 1152.880 / 1111.732 / 13.611 |

Untracked paths, sizes, line counts and exact hashes are in
[the inventory](evidence/rollout-hardening-1.3.3/round-01-inventory.json).
No binary additions, deletions of upstream tests, reward-file manipulation or
successful answer retrieval were observed. Ordinary Base history inspection,
empty WebSearch results, missing gh and blocked curl/WebFetch requests are not
answer leakage. CLI cost/token accounting is not used as a billing estimate.

- **8z** introduced range/extent helpers, compact storage and row accounting.
  An early prompt-index-versus-row-index bug was found by its own test and
  corrected. It still looks up a cache entry before checking whether a cold
  window consumes any embedding, causing the real gather path to fail. It
  also assumes analytical maxima already count rows and misses Qwen3 video
  inflation. Final focused tests: 21 passed, 2 deselected. Broader scheduler,
  processing and utility tests failed mainly on unavailable model configs or
  media assets; these did not supply coverage for the missing behavior.
- **Ks** coherently changed batching output from `(hash, position)` pairs to
  hashes, including its production caller. The original verifier replaced the
  producer with the old shape and caused bogus cache misses. After producer
  repair, the same captured answer passes cache lifecycle challenges. Its
  unchanged Qwen3 analytical estimator still yields inflated capacity. Final
  focused tests: 50 passed, 1 skipped. A reuse probe initially omitted cache
  allocation; the agent corrected that test fixture and confirmed reuse.
- **RfY** repaired row accounting, sparse gathering, cold empty windows and the
  union of main/lookahead needs. It added separate profiling accessors but
  copies analytical maxima to both coordinate spaces, missing video inflation.
  Its focused tests actually ran: 23 passed. New model-dependent scheduler
  tests could not run with unavailable HF configs; the final answer disclosed
  that limit. Incorrect ad-hoc window expectations were corrected rather than
  removed to suppress a real production failure.
- **tBc** correctly handles cold empty gather, raw cache storage and row charging,
  but shifts the entire scheduling window. Main-window-only embeddings can be
  missed when lookahead is empty. Its video estimator also remains inflated.
  Its profiling conservatively retains a larger full-span buffer, which is
  allowed. Cache/mapping tests: 16 passed; request test: 1 passed. Standalone
  scheduler/gather/reuse probes passed but omitted the main-only lookahead case.
  Gather assertions first used absolute prompt positions; correcting them to
  batch-local positions was valid.

Original 8-stage worker failures: 8z failed scheduled cache lifecycle (and
fresh observations); Ks failed partial mapping and model-runner gather due to
the fixture. RfY and tBc completed the eight stages but failed the independent
fresh-observation comparison. In 1.3.3, 8z fails one of nine stages plus fresh
observations; the other three complete all nine stages and fail fresh video
capacity observations (tBc also lookahead). These counts describe required
stages, not numbers of pytest cases. All four jobs completed with reward files
and without Harbor infrastructure exceptions; zero process exit alone was not
accepted as success.

## Reproduced behavior matrix

| Captured answer | Cache lifecycle challenge after fixture repair | Independent video capacity | Runtime/profile storage coverage | Revised full reward |
|---|---|---|---|---:|
| 8z | fail: cold empty gather cache miss | fail | pass | 0 |
| Ks | pass | fail | pass | 0 |
| RfY | pass | fail | pass | 0 |
| tBc | fail: main embedding omitted by shifted-only check | fail | pass, conservative overestimate | 0 |

These are development diagnostics on saved answers, not fresh model successes
or held-out capability measurements. Pre-run snapshots and post-run unchanged
checks accompany each replay. The original-revision replay also reproduced all
four original zeros. The 1.3.1 fixture-only correction changed Ks's causal
failure, not its complete reward.

## Repairs and contract basis

**Batch producer fixture (1.3.1, bd66332).** Scheduled media -> real
`_batch_mm_kwargs_from_scheduler` -> real encoder/cache writer -> real gather
must preserve rows and prompt masks. Internal batching return shape is explicitly
free. Replacing the batch producer imposed an old private API. The repaired
fixture supplies external fake media tensors and leaves the real producer and
consumer connected. A hash-only alternative fails the old grader and passes
the repaired full grader; no candidate-identifying adapter is used.

**Video dummy producer (1.3.2, 053ffb7).** The direct estimator fixture now also
supplies a valid two-frame dummy placeholder (11 non-embedding prefix positions,
visual rows, one suffix per frame), so an implementation deriving full-span
profiling values from normal dummy preprocessing remains possible. Real Qwen3
estimation, registry, scheduler capacity and worker capacity stay active. A
second independent challenge uses four frames and different row counts. Expected
16/48 encoder rows versus observed 200/600 (independent challenge 32/80 versus
400/1000) proves the remaining candidate bug. The old fixture incorrectly lacked
a producer required by a legitimate alternative; expectations were not weakened.

**Runtime/profile memory coverage (1.3.3, d85f6ad).** The instruction requires
profiling and runtime caching to stay consistent. Base `profile_run` explicitly
reserves encoder-cache storage during decoder profiling, making this obligation
discoverable. See [the case contract](profile-runtime-case.md). The earlier
`alternate-dense-cache.patch` kept dense runtime storage but compact profiling:
444 live bytes versus 48 profiled, and 1220 versus 120 for a second width/shape.
It historically scored 1; the new stage correctly makes it 0. Its historical
patch/evidence are preserved. The new complete `alternate-dense-profile-consistent`
control retains dense storage and adjusts profiling, and scores 1. Exact storage
equality was used only in an early diagnostic; scoring allows conservative
preallocation (`profiled >= live * items`). No observed all-zero rate motivated
removing requirements or manufacturing successful attempts.

No scored overlapping-placeholder case was added from the provisional
first-embedding-order hypothesis: supported producer/runner ordering semantics
need separate investigation, and a possible pre-existing overlap limitation is
not sufficient to expand this task's repair contract.

## Final executable acceptance

Actual Harbor canary 05 applied Oracle, captured final state, ran the new stage
through the real grading path and returned reward 1. Inputs remained unchanged.
Complete fixed-image test.sh acceptance at d85f6ad matched **27/27** expected
rewards, including compact/direct-mask, renamed-cache, distinct-accessor,
request-initialized-count, hash-only batching and consistent dense alternatives.
Base and incorrect/forgery/early-exit controls remain rejected. This matrix is
actual Docker grading; it is not mislabeled as 27 Harbor runs.

All four saved answers were restored with tracked and untracked state on the
pinned image, regraded, and run against the two independent challenges. Restore
and post-state checks succeeded and frozen inputs did not change. The limitation
about missing original outside-repository state still applies.

Security claim is limited to the tested completion-channel bypasses and reviewed
observable behavior. Candidate Python executes with in-process instrumentation;
this is not a proof against arbitrary native-code or process-memory attacks.
CPU storage observation does not establish full CUDA allocator peak correctness,
real pretrained-model inference, all model families or distributed deployment.
No claim of universal verifier correctness follows from these finite checks.
Within the stated contract and tested boundaries, the demonstrated fixture
errors and coverage gap are repaired, with no remaining confirmed blocker.


## Second frozen batch and stop decision

A100 `/tmp/pr84-flash-round-02`, executable `d85f6ad`, task 1.3.3,
Harbor task checksum `47f923b4c484b5c92423b55d8b4eeefd4531a5c75086df1edbe5e6f3cbd20e77`.
Four attempts ran concurrently with no retries. All completed, no Harbor errors,
and all after-agent capture hashes passed. The campaign lasted 1811.659 seconds
(about 30 minutes 12 seconds). Frozen task input checks remained clean. Job-level
naive timestamps and trial UTC timestamps use different timezone renderings;
durations are computed within each timestamp series.

| Trial | Original / saved replay reward | Agent/total steps | ATIF tools | Tracked + untracked files | Tracked +/− | Total / agent / verifier seconds |
|---|---:|---:|---:|---:|---:|---|
| task__7zizsQC | 0 / 0 | 174/176 | 216 | 11+1 | +397/−93 | 1141.588 / 1100.139 / 14.446 |
| task__AY322Nc | 0 / 0 | 211/212 | 219 | 8+0 | +344/−102 | 1810.579 / 1770.332 / 14.047 |
| task__DNeUYoB | 0 / 0 | 219/222 | 248 | 8+2 | +242/−90 | 1180.989 / 1140.456 / 14.251 |
| task__EtZi3Zs | 0 / 0 | 155/156 | 164 | 9+1 | +379/−76 | 1290.098 / 1249.748 / 14.367 |

All four pass the nine required worker stages, including runtime/profile storage
coverage, but fail fresh `direct_profile` observations: expected scheduler and
runner budgets 16/48, observed 200/600. Independent four-frame challenges expect
32/80 and observe 400/1000. Their ordinary dummy-input sparse/dense/empty capacity
cases pass. This is the real analytical video-estimator path, not a test of new
accessor names or an exact choice of cache representation.

| Second-batch answer | Independent cache lifecycle | Independent video capacity | Runtime/profile coverage | Attribution |
|---|---|---|---|---|
| 7z | pass | fail | pass | incomplete analytical-estimator repair |
| AY | pass | fail | pass | copies analytical count to both coordinates |
| DNe | pass | fail | pass | leaves analytical estimator unchanged |
| EtZi | pass | fail | pass | analytical count copied; batch item limit also uses prompt span |

Confidence is high for the reproduced video defect and resulting zeros. Passing
individual columns is scoped to those checks, not a claim that any whole answer
is correct.

- **7z** repairs row accounting, raw caching and the union of main/lookahead.
  It fixes its own allocation-order and prefix-sum test errors. Final focused
  cache/scheduler tests: 35 passed; EC connector: 24 passed, 1 skipped. Its final
  summary's earlier count of 57 is stale, not evidence of another completed run.
  HF/device and absent tooling limited broader tests. Analytical maxima are
  incorrectly treated as already being encoder rows.
- **AY** adds first/last embedding helpers, raw storage and early release; separate
  profiling accessors still duplicate the analytical maximum. It compares
  selected failing MM/scheduler tests with Base; KV tests were 6 failed/34 passed
  on both, and priority tests 12 failed on both. Cache 9 plus prefix 30 passed;
  ad-hoc scheduler checks, 4000 positive-length dense scheduler comparisons and
  3000 gather comparisons passed. Zero-length inputs were excluded from its
  old/new equivalence test because their intended behavior changes. No new
  repository tests were delivered; temporary scripts are visible in the trace.
  Its final claim about every scheduler test failing is broader than the selected
  comparison run. An accidental registry syntax edit was immediately repaired
  and imports rechecked.
- **DNe** repairs accounting, raw cache, empty windows and early release. A model
  review subagent raises shape validation and chunk-boundary questions; the
  final answer adds an output-row assertion for masked items. This timing choice
  is not made a hidden verifier requirement. Focused tests: 26 passed; EC tests:
  24 passed, 1 skipped. Its initial reuse test forgot allocation and was repaired.
  The review subagent also misses the analytical video path.
- **EtZi** uses raw storage, correct empty-window handling and a global output
  shape assertion, while retaining prompt-span assumptions in analytical
  profiling and per-batch item limits. Focused tests: 16 passed. Its own random
  fixture corrections address invalid empty feature lists and double-counted
  compute budget; subsequent dense/masked differential checks pass. Broader MM
  tests (75 failed, 107 passed, 1 xfailed, 28 errors) were not all rerun on Base,
  so this review does not certify all those failures as pre-existing.

No observed successful answer retrieval, reward manipulation, or test suppression
explains these outcomes. Empty search results, blocked fetches, Base-only history
inspection and reading the older installed vLLM are recorded as such. Agent test
edits largely add behavior coverage or repair their own fixtures. A speculative
overlap-order problem remains outside the scored additions for the contract
reason given above.

Complete delivered repositories, including untracked tests, were restored on the
pinned image and regraded in four parallel replay containers. All cache challenges
passed; all video challenges failed; all post-state checks reported no changes to
existing non-pyc files. Replay input hashes also remained unchanged. The original
second-batch containers were retained and their full `docker diff` inventories
were inspected. Outside-repository changes consist of harness `/tests`, capture
and CLI files, temporary diagnostics, pytest caches and ordinary Torch/TVM/FlashInfer
runtime-generated caches (including the TVM CPU addon). No intentional installed
package patch or successful package install was observed. These are post-verifier
inventories, not an after-agent whole-container snapshot; bind-mounted CLI logs
are covered by the archived trajectory rather than Docker diff.

The 1.3.3 executable did not change after this batch. No third batch is justified
by an unconfirmed hypothesis or a wish to produce a passing flash answer. Oracle
and diverse full-scoring positive controls establish concrete solvability, while
the negative controls and saved-answer challenges exercise rejection behavior.
This is development validation, not an unbiased model-capability estimate.

## Evidence handoff

The checked-in [evidence directory](evidence/rollout-hardening-1.3.3/) contains
both inventories, actual Harbor canary/job records, immutable-input checks,
replay diagnostics, the full control matrix, Docker diff inventories and a hashed
review ledger. `evidence-files.sha256.json` inventories its files. Credential
values are not included; configuration references use environment placeholders.
Full native/ATIF trajectories and final repository archives remain on A100 in
`/tmp/pr84-flash-round-01` and `/tmp/pr84-flash-round-02`, with local archives in
`outputs/pr84-flash-review/round-01` and `round-02` in the curator workspace.
Archive hashes are recorded in `campaign-archive-hashes.json`. Historical 1.3.0
review/e2e records describe their original revision and are superseded for this
campaign by this report. Final documentation/evidence commit is separate from
the executable revision; no repeated model run is needed for that documentation.
