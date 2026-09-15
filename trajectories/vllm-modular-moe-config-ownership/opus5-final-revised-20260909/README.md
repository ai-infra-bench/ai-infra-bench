Adds a modular MoE configuration-ownership task. Kernels and affected consumers must follow the active layer, preserve worst-case profile workspace, and support compatibility construction without process-global state.

Latest Opus 5 run: **reward 0**, **zero Harbor errors**. The agent retained a global-config fallback in compatibility construction, contrary to the public contract. Historical score is unchanged. Job `4599fb20-e615-4f74-bb3c-258399d432e8`, trial `708e833d-2a03-43e0-8197-a9e293853f83`.

- [trajectory.json](trajectory.json): browsable ATIF (70 steps).
- [trace-bundle.tar.gz](trace-bundle.tar.gz): complete API JSONL, Tap SQLite, Claude Code log, job/trial results and verifier outputs.
- [manifest.json](manifest.json): original/export hashes, evaluated task identity and authentication-field redactions.
- [review.md](review.md): three-gate review, attribution and limitations.
- [publication-checks.json](publication-checks.json): checks and fresh final Oracle result.
- [publication-oracle.tar.gz](publication-oracle.tar.gz): portable raw evidence for that Oracle run.

Local skill review passed. The unchanged 16-run Harbor matrix and nine independent challenges were hash-checked; one additional publication Oracle passed all six groups. Remote CI and maintainer approval are separate.

Verify archive SHA-256 values using the JSON manifests before extracting into an empty directory. The SQLite database in the trace bundle is agent/traces.sqlite3. Authentication values were redacted in publication copies; local originals were not changed. Candidate source/native binaries and image binaries are not uploaded; tool edits, commands, pinned image recipe and dependency locks are supplied.

Task: [vllm-modular-moe-config-ownership](../../../tasks/vllm-modular-moe-config-ownership). Task version 1.2.6; Base e2ed238885be6af358be1851cd43105b7d036c49. Task evidence includes portable control logs; absolute local paths identify their original host records.
