Adds an asynchronous pipeline-parallel token-handoff task requiring GPU-tensor communication, retained/discarded request bookkeeping and overlapping scheduler rounds.

The new Opus 5 run received reward 0 because its handoff calls broadcast_object for request IDs. CONFIG and SCHEDULER_REENTRY passed; BASIC, INTEGRATED and REORDERED NCCL phases rejected object communication. This is a solver failure, not an Oracle failure.

Real GPUModelRunner construction and two-rank NCCL handoff through production sample_tokens, plus real scheduler reentry. Controlled model/sampler inputs substitute computation outside the transport/state boundary.

Original reward: **0**; Harbor errors: **0**. Job `8c795763-9465-4397-8cca-b3e8b145cbc1`, trial `5e0c1ca2-934a-425f-ad46-ebdc03943079`. Model: `claude-opus-5`.

- [trajectory.json](trajectory.json): browsable ATIF.
- [trace-bundle.tar.gz](trace-bundle.tar.gz): ATIF, Claude Code output, API JSONL, sanitized Tap SQLite, job/trial results and verifier logs.
- [manifest.json](manifest.json): original/export hashes, task/prepared hashes, redactions and archive integrity.
- [publication-checks.json](publication-checks.json): repository validation, strict artifact audit and CI helper compatibility.
- [review.md](review.md): publication review scope and three-gate assessment.

Publication copies redact authentication fields and recognizable credentials. SQLite is rebuilt so removed credentials cannot remain in free pages. Raw local logs/rewards remain unchanged. Candidate source trees/native binaries are omitted from this portable bundle; successful edits and commands remain in the trajectories. PR18 did not export a complete final candidate tree in its original run.

Verify trace-bundle.tar.gz against the SHA256 in manifest.json, then extract into an empty directory. The database is agent/traces.sqlite3; PRAGMA integrity_check should return ok.

Task evidence under validation/e2e-evidence.json records the fresh final Oracle; historical controls remain in validation/history/pre-publication-formatting-evidence.json with their original hashes. Its local paths identify original host records, not public download URLs. Image binaries remain on the evaluation host; the PR supplies the pinned build recipe and locks, not a registry upload.

The preparation helper retains Oracle-relative control behavior and parses Harbor 0.22 reward statistics; 32 prepared case trees across these three tasks match the reviewed helper byte-for-byte. The skill review is local, not GitHub reviewer approval. Historical documents saying uncommitted describe their original validation state.

Task: [tasks/vllm-async-pp-token-handoff](../../../tasks/vllm-async-pp-token-handoff). Base `8ebf372e9d612a325f54aadf5c0c3c6588b6afa3`; task version `1.2.2`.

Publication update: final Harbor Oracle reward 1, zero errors, trial `21d71be3-385a-4bde-9881-bd05b09ba05c`. The Opus trajectory is unchanged and was not rerun for formatting. See `validation/publication-formatting.json` in the task for exact changes and portable final-run logs.
