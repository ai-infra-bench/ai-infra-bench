Opus 5 evaluation: vllm-int8-per-token-group-quantization

Adds a native INT8 per-token-group quantization task covering correctness, dispatch and fallback behavior, and speedup against a frozen Triton reference.

Original reward: **1**. Model identifier: `claude-opus-5`; Claude Code Tap 2.1.238. This is an archived 2026-09-09 solver run, not a newly generated trajectory.

The archived solver passed native build, correctness, dispatch/fallback and five performance cases. Speedups were 2.349, 2.745, 5.146, 2.732 and 5.389 against a 1.5 minimum.

Job: `5b814933-fff8-4d8a-9669-cc051ecdcb07`. Trial: `9ad54cd3-3ac3-44d3-a450-9bba111f91c0`. Harbor errored trials: 0.

Real CUDA/native operator and independent frozen reference on one A100; candidate sources are rebuilt before grading.

- [trajectory.json](trajectory.json): browsable Harbor ATIF trajectory.
- [trace-bundle.tar.gz](trace-bundle.tar.gz): ATIF, Claude Code stream JSON, API JSONL, sanitized Tap SQLite, original job/trial results and configuration, and verifier logs.
- [manifest.json](manifest.json): per-file original/export SHA-256, bundle hash, exact task-file hashes, redaction scope and known limitations.
- [publication-checks.json](publication-checks.json): packaging checks and preparation equivalence to the previously reviewed CI helper.

Extract the archive with `tar -xzf trace-bundle.tar.gz -C <empty-directory>`. The exported database is `agent/traces.sqlite3`; `PRAGMA integrity_check` must return `ok`. Verify the bundle SHA-256 against manifest.json before use.

Publication copies remove authentication header/key values and recognizable credentials. Original local artifacts and rewards are unchanged. The SQLite database is rebuilt into a fresh file; table/record counts are preserved and blob bodies are unchanged. Candidate repository trees/native binaries and unrelated session state are omitted; the commands and edits remain in the trajectories.

Task files match the reviewed version byte-for-byte. The task image is retained on the evaluation host; the 10–12 GB image itself is not uploaded in this PR and historical absolute log paths remain provenance, not public download URLs. The checked-in environment recipe/locks and this portable solver archive are available to reviewers. Repository CI must build or obtain the image on a matching runner. No new solver rerun or external reviewer approval is claimed.

Task: [tasks/vllm-int8-per-token-group-quantization](../../../tasks/vllm-int8-per-token-group-quantization). Upstream context: https://github.com/vllm-project/vllm/pull/21476. Base: `14bf19e39f601163265b7c7d58d972b8a83d8896`.
