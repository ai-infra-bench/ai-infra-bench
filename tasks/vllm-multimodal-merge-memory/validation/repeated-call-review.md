# Repeated-call verification hardening — v1.3.3

The task can be retained. The repeated-call false acceptance is fixed and validated through the real scorer and Harbor. This is a scoped verifier repair; the previously noted unrelated donor-source cutoff inconsistency remains an environment follow-up, with no demonstrated merge-answer exposure. All ten dimensions are scored, 19/20; this does not assert that every task acceptance issue is closed.

| # | Dimension | Score | Evidence / gap | Next action |
|---|---|---:|---|---|
| 1 | Realistic and clear task | 2 | Existing instruction explicitly requires correctness across repeated calls | — |
| 2 | Independent contract | 2 | Expected output follows current mask and embedding order | — |
| 3 | Solvable environment and cutoff | 1 | Real A100 execution passes; unrelated post-cutoff installed source remains | Environment follow-up |
| 4 | Bidirectional coverage | 2 | New CPU/CUDA cases vary positions, values and text rows across calls | — |
| 5 | Real semantic path | 2 | Real production merge and CUDA tensors; only model-produced data substituted | — |
| 6 | Correct alternatives accepted | 2 | Boolean indexing, index_copy and content-keyed caching all pass | — |
| 7 | Incorrect implementations rejected | 2 | Stale placement fails on its second call; all retained negative controls reject | — |
| 8 | Oracle independently validated | 2 | Independent review challenge and current full suite both pass | — |
| 9 | Completion integrity | 2 | Authenticated checkpoints; both early-exit controls also reject through Harbor | Retain bounded threat model |
| 10 | Reproducibility | 2 | Frozen executable hashes, raw logs, Harbor checksums and full-state replays retained | — |

## Behavioral change and implementation independence

The previous 32-case suite reused identical inputs in its repeated allocation measurements. A curator-created implementation cached the first mask by length and placeholder count, then wrote later embeddings to obsolete positions. It earned reward 1 through Harbor. This control is a diagnostic counterexample, not a claim that a submitted model answer used that optimization.

Two appended cases bring the suite to 34. Each makes three calls with the same destination shape and placeholder count, updating the mask, source tensor and original text rows in place. The placeholder positions differ each time. Expected outputs are computed on the CPU from the current inputs. Assertions inspect returned identity, dtype, complete output values, and the existing CPU-mask synchronization contract. They do not inspect caches, helpers, candidate source, algorithm names or intermediate representations.

The positive `content-keyed-placement-cache` control explicitly demonstrates that caching remains allowed. The materially different existing index_copy implementation is also retained. Control patches live only in curator validation artifacts; the scoring suite never reads them.

The semantic boundary is: consecutive valid masks and CUDA embeddings → real production merge → current-call ordered in-place output with unchanged non-placeholder rows. Equal lengths and cardinalities do not constrain the positions of multimodal tokens in subsequent requests/chunks. The task explicitly requires repeated-call correctness. Generated embedding values replace model forward; no scheduler, HTTP server or model weights are needed for this indexing transition. Both mask devices are covered. Source and destination buffers are reused, but candidates may choose any valid internal representation.

Gate 1 remains passed. Gate 2 execution is established, while the separate source-cutoff follow-up remains open. Gate 3's confirmed repeated-call gap is closed on the unchanged image. No instruction, Oracle, image or scoring-supervisor change was required. The C checkpoint emitter and parent authentication checks are unchanged.

## Actual validation

Image: `sha256:9b8b0bfbce07832a29b5831c05726ca795f00eface39d678b9a9aea20646d51b`; NVIDIA A100-SXM4-40GB; PyTorch 2.10.0+cu129. Each container used one GPU, 4 CPUs, 16 GiB RAM and disabled networking. Validation used available devices 2–7 with one active candidate per device. No paid model run was started.

The initial smoke passed Oracle and content-keyed caching and rejected stale placement. The subsequent full matrix completed 18/18 expected outcomes, including repeated Oracle and index_copy trials:

| Control | Expected / actual reward | Completed checks | Final observation |
|---|---|---|---|
| base | 0 / 0 | 0/34 | ValueError: Error during masked scatter operation |
| alternative-agent-implementation | 1 / 1 | 34/34 | PASS: repeated_merge_cuda: {'passed': True} |
| legacy-alternative | 0 / 0 | 6/34 | AssertionError: temporary allocation is excessive: cuda 5.509 |
| early-exit-systemexit | 0 / 0 | 0/34 | SystemExit: 0 |
| forged-success-exit | 0 / 0 | 0/34 | PASS: production merge is ordered, async, bounded, strict, and CPU-mask native |
| cuda-extra-allocation | 0 / 0 | 6/34 | AssertionError: temporary allocation is excessive: cuda 6.003 |
| cpu-sync | 0 / 0 | 0/34 | AssertionError: CPU-mask merge explicitly waited for CUDA |
| stale-placement-cache | 0 / 0 | 32/34 | AssertionError: repeated merge used incorrect positions or values: mask_device=cpu, call=2 |
| oracle-repeat | 1 / 1 | 34/34 | PASS: repeated_merge_cuda: {'passed': True} |
| oracle | 1 / 1 | 34/34 | PASS: repeated_merge_cuda: {'passed': True} |
| legacy-oracle | 0 / 0 | 14/34 | AssertionError: cardinality mismatch 1!=3 accepted |
| incomplete-agent-implementation | 0 / 0 | 0/34 | ValueError: Error during masked scatter operation |
| early-exit-os-exit | 0 / 0 | 0/34 | os._exit(0) before any checkpoint; child_status=0 |
| forged-checkpoint-callback | 0 / 0 | 0/34 | RuntimeError: checkpoint did not originate in the trusted suite |
| reverse-rows | 0 / 0 | 0/34 | AssertionError: embedding order, values, or non-placeholder rows changed |
| cpu-implicit-sync | 0 / 0 | 0/34 | RuntimeError: called a synchronizing CUDA operation |
| content-keyed-placement-cache | 1 / 1 | 34/34 | PASS: repeated_merge_cuda: {'passed': True} |
| alternative-repeat | 1 / 1 | 34/34 | PASS: repeated_merge_cuda: {'passed': True} |

All successful matrix runs completed 34 authenticated checks, child_status=0, errors=[]. All successful controls preserved the existing peak-allocation bound. The stale-placement failure is `mask_device=cpu, call=2`, after the original 32 checks have passed. Base still fails on the requested CPU-mask merge path; integrity controls reach the intended candidate import boundary.

Harbor 0.22.0 independently completed six trials with no framework exceptions. Canonical task and prepared inputs were unchanged across each run. Prepared copies only select a GPU and, for control trials, replace the Oracle patch with that candidate; grading files remain identical:

| Harbor candidate | Reward | Completed checks | Trial |
|---|---:|---:|---|
| oracle | 1 | 34/34 | oracle__fQh3bwp |
| alternative | 1 | 34/34 | alternative__2kJN6eM |
| early-exit-systemexit | 0 | 0/34 | early-exit-systemexit__nYurSX8 |
| stale-placement-cache | 0 | 32/34 | stale-placement-cache__XbjN588 |
| content-keyed-placement-cache | 1 | 34/34 | content-keyed-placement-cache__ihREPZi |
| early-exit-os-exit | 0 | 0/34 | early-exit-os-exit__JGoYubz |

The four previously recorded GPT-6 medium answers were restored from their complete final repository archives, including tracked, untracked and ignored files. Archive SHA-256 values matched the captured manifests before execution and were unchanged afterward. This was regrading saved answers, not generating new ones:

| Original trial | Original v1.3.2 result | v1.3.3 complete-state replay |
|---|---|---|
| codex-gpt6-medium-r03-gpu0__BnWSbdd | 1 (32/32) | 1 (34/34) |
| codex-gpt6-medium-r03-gpu2__Qt4qny2 | 1 (32/32) | 1 (34/34) |
| codex-gpt6-medium-r03-gpu1__iBKe4DE | 1 (32/32) | 1 (34/34) |
| codex-gpt6-medium-r03-gpu3__kzaY4Pk | 1 (32/32) | 1 (34/34) |

## Evidence and snapshot

Starting task revision: `5a8b78f293f48ad6d317164beaa152857f588618`. Base: `36d7f19897843c9cbdb701ba88d0f2c29954fe44`. Skill source: `/home/qunhong/workspace/ai-infra-bench/.agents/skills/ai-infra-bench-task-review`, repository HEAD `9a5d7fee81b151a362b13a67587a12fc8cc00296`; loaded skill files were unmodified. The user authorized this specific coverage repair, implementation-independent verification and a push to PR #63.

Final executable hashes:

- `tests/case_specs.py`: `ad0318f598f6bbfcc399441e23d6ab61717d7be76d625c51d421742438971047`
- `tests/verify_multimodal_merge.py`: `9c0f371662937673c517a923727aa925be028d9fd8b96e03dd6ca43ff2dc6fbd`
- `task.toml`: `9001eb11bce12f1a1c4e17da295c413550686d966348f99e6b0a3e41ca2d1874`
- `validation/ci-cases.json`: `7cb6e0ae2619aaef6ecb7038e78c47053a3a7664d87440e45ff7c2cb64acb7e0`
- `validation/stale-placement-cache.patch`: `44b2f311378edb9d462f1e6e92750d096203c3f8d73e22e33fff2fffc65bf750`
- `validation/content-keyed-placement-cache.patch`: `2e6ee3dce743faece9e359f56a4dee6b177840ad240c234cd62cdb99dbfbe66d`

`repeated-call-evidence.zip` contains commands, frozen inputs, smoke/matrix/replay results, Harbor trial results and completion logs, validation scripts, original false-acceptance evidence and a per-file SHA-256 manifest. Full model-answer archives remain on A100 at the paths recorded in replay results, as before. `e2e-evidence.json` indexes this revision; the previous index is preserved as `history/v1.3.2-evidence.json`. Historical 26/32-case results are not relabeled as 34-case results. `ci-cases.json` now contains control definitions only; observed results belong to versioned evidence.

Executable files were frozen before validation. Final documentation and evidence were written after runs, so whole-directory checksums include the recorded pre-evidence snapshot; all executable hashes were rechecked against frozen inputs. The image was reused because environment inputs did not change. Root-owned scoring output collection and the original 36000-second agent budget remain unchanged. This verification retains the existing limitations concerning arbitrary native observer tampering and full Qwen serving.
