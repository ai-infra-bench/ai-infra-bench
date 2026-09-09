Adds a fused-MoE configuration-lifecycle task: configured profiling/forward must use the active layer configuration without false missing-config warnings, while genuinely missing configuration must still warn.

The new Opus 5 run passed all five groups: configured profile, lifecycle gap, genuine missing-config warning, active-layer precedence, and real Triton numerical behavior.

Real quant-method initialization, production factory/kernel profiling and Triton forward on A100. Controlled layer/input views preserve configuration relationships; weight loading and transport are outside this boundary.

Original reward: **1**; Harbor errors: **0**. Job `5cf1558a-9007-4857-beda-80c2ece5a701`, trial `e1445751-bace-4db6-84f5-b42f0f4974c2`. Model: `claude-opus-5`.

- [trajectory.json](trajectory.json): browsable ATIF.
- [trace-bundle.tar.gz](trace-bundle.tar.gz): ATIF, Claude Code output, API JSONL, sanitized Tap SQLite, job/trial results and verifier logs.
- [manifest.json](manifest.json): original/export hashes, task/prepared hashes, redactions and archive integrity.
- [publication-checks.json](publication-checks.json): repository validation, strict artifact audit and CI helper compatibility.
- [review.md](review.md): publication review scope and three-gate assessment.

Publication copies redact authentication fields and recognizable credentials. SQLite is rebuilt so removed credentials cannot remain in free pages. Raw local logs/rewards remain unchanged. Candidate source trees/native binaries are omitted from this portable bundle; successful edits and commands remain in the trajectories. PR18 did not export a complete final candidate tree in its original run.

Verify trace-bundle.tar.gz against the SHA256 in manifest.json, then extract into an empty directory. The database is agent/traces.sqlite3; PRAGMA integrity_check should return ok.

Task evidence under validation/e2e-evidence.json records the fresh final Oracle; historical controls remain in validation/history/pre-publication-formatting-evidence.json with their original hashes. Its local paths identify original host records, not public download URLs. Image binaries remain on the evaluation host; the PR supplies the pinned build recipe and locks, not a registry upload.

The preparation helper retains Oracle-relative control behavior and parses Harbor 0.22 reward statistics; 32 prepared case trees across these three tasks match the reviewed helper byte-for-byte. The skill review is local, not GitHub reviewer approval. Historical documents saying uncommitted describe their original validation state.

Task: [tasks/vllm-fused-moe-config-lifecycle](../../../tasks/vllm-fused-moe-config-lifecycle). Base `2902c348265639de300c95cbcae1c26486f57ac7`; task version `1.2.5`.

Publication update: final Harbor Oracle reward 1, zero errors, trial `384c222c-a54d-430f-a297-eab8e5b565ec`. The Opus trajectory is unchanged and was not rerun for formatting. See `validation/publication-formatting.json` in the task for exact changes and portable final-run logs.
