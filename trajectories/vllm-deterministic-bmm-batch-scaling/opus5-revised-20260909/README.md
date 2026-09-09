Adds a deterministic batched-matrix-multiplication task: replace per-item launches with a batch-aware Triton kernel while preserving numerical/bitwise behavior and existing out-copy compatibility.

The new Opus 5 run passed correctness, output-copy/error contracts, launch scaling and performance. Speedups on the three public workloads were 3.9136x, 6.3760x and 1.1491x, above the unchanged 2.0x/1.05x/1.05x thresholds.

Real A100 CUDA/Triton multiplication and output copies. Model serving is outside this tensor-operation boundary.

Original reward: **1**; Harbor errors: **0**. Job `ff5dcfa0-2875-4470-bb6e-3c2be4d31d2e`, trial `5b689dc0-2b52-41ab-b15a-84d899dcff1d`. Model: `claude-opus-5`.

- [trajectory.json](trajectory.json): browsable ATIF.
- [trace-bundle.tar.gz](trace-bundle.tar.gz): ATIF, Claude Code output, API JSONL, sanitized Tap SQLite, job/trial results and verifier logs.
- [manifest.json](manifest.json): original/export hashes, task/prepared hashes, redactions and archive integrity.
- [publication-checks.json](publication-checks.json): repository validation, strict artifact audit and CI helper compatibility.
- [review.md](review.md): publication review scope and three-gate assessment.

Publication copies redact authentication fields and recognizable credentials. SQLite is rebuilt so removed credentials cannot remain in free pages. Raw local logs/rewards remain unchanged. Candidate source trees/native binaries are omitted from this portable bundle; successful edits and commands remain in the trajectories. PR18 did not export a complete final candidate tree in its original run.

Verify trace-bundle.tar.gz against the SHA256 in manifest.json, then extract into an empty directory. The database is agent/traces.sqlite3; PRAGMA integrity_check should return ok.

Task evidence under validation/e2e-evidence.json records the fresh final Oracle; historical controls remain in validation/history/pre-publication-formatting-evidence.json with their original hashes. Its local paths identify original host records, not public download URLs. Image binaries remain on the evaluation host; the PR supplies the pinned build recipe and locks, not a registry upload.

The preparation helper retains Oracle-relative control behavior and parses Harbor 0.22 reward statistics; 32 prepared case trees across these three tasks match the reviewed helper byte-for-byte. The skill review is local, not GitHub reviewer approval. Historical documents saying uncommitted describe their original validation state.

Task: [tasks/vllm-deterministic-bmm-batch-scaling](../../../tasks/vllm-deterministic-bmm-batch-scaling). Base `b07555d26f4c7ad9a2d1ec45428a9d4287db612c`; task version `1.2.3`.

Publication update: final Harbor Oracle reward 1, zero errors, trial `d99548dc-e65c-4a2c-9137-6cdc91dd7e69`. The Opus trajectory is unchanged and was not rerun for formatting. See `validation/publication-formatting.json` in the task for exact changes and portable final-run logs.
