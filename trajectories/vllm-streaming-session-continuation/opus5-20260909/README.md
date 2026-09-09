Opus 5 evaluation: vllm-streaming-session-continuation

Adds a streaming continuation state-transition task covering reuse of existing sessions, unique batch membership, token absorption and refreshed sampling/generator/pooling state.

Original reward: **0**. Model identifier: `claude-opus-5`; Claude Code Tap 2.1.238. This is an archived 2026-09-09 solver run, not a newly generated trajectory.

The archived solver received reward 0: repeated continuation duplicated batch rows and did not refresh required request parameters. This is retained as a genuine solver failure; it is not presented as an Oracle failure.

Job: `16bdc7c4-7224-45b5-b66c-57dce84e13bc`. Trial: `489ac565-35b7-4de3-8b2c-f2f6015d8ee1`. Harbor errored trials: 0.

Real InputBatch, CachedRequestState and GPUModelRunner._update_states at the continuation-state boundary, with deterministic upstream records. This is not a full serving-service or full GPU runner initialization test.

- [trajectory.json](trajectory.json): browsable Harbor ATIF trajectory.
- [trace-bundle.tar.gz](trace-bundle.tar.gz): ATIF, Claude Code stream JSON, API JSONL, sanitized Tap SQLite, original job/trial results and configuration, and verifier logs.
- [manifest.json](manifest.json): per-file original/export SHA-256, bundle hash, exact task-file hashes, redaction scope and known limitations.
- [publication-checks.json](publication-checks.json): packaging checks and preparation equivalence to the previously reviewed CI helper.

Extract the archive with `tar -xzf trace-bundle.tar.gz -C <empty-directory>`. The exported database is `agent/traces.sqlite3`; `PRAGMA integrity_check` must return `ok`. Verify the bundle SHA-256 against manifest.json before use.

Publication copies remove authentication header/key values and recognizable credentials. Original local artifacts and rewards are unchanged. The SQLite database is rebuilt into a fresh file; table/record counts are preserved and blob bodies are unchanged. Candidate repository trees/native binaries and unrelated session state are omitted; the commands and edits remain in the trajectories.

Task files match the reviewed version byte-for-byte. The task image is retained on the evaluation host; the 10–12 GB image itself is not uploaded in this PR and historical absolute log paths remain provenance, not public download URLs. The checked-in environment recipe/locks and this portable solver archive are available to reviewers. Repository CI must build or obtain the image on a matching runner. No new solver rerun or external reviewer approval is claimed.

Task: [tasks/vllm-streaming-session-continuation](../../../tasks/vllm-streaming-session-continuation). Upstream context: https://github.com/vllm-project/vllm/pull/28973. Base: `0118cdcc02ae16a137645e2289bf41f5e3da9d80`.
