# Frozen construction handoff

Review with `.agents/skills/ai-infra-bench-task-review/SKILL.md`, beginning with
the statement and environment before reading the Oracle. Construction is not
independent approval. No independent release review or solver pilot is claimed.

The target boundary is scripted model calls through real Pi tools, context
reconstruction, append-only session persistence, and the next actual model HTTP
request. Only model responses and ordinary external evidence are substituted.

Use `source-reference.json` for the Codex implementation reference and the local
Pi adaptations. The Codex backend itself is not shipped or invoked. Use
`coverage.json`, `ci-cases.json`, and `construction.json` for behavioral mapping
and validated controls. `docker-runtime-hashes.json` identifies the exact
runtime files tested remotely; `artifact-hashes.json` identifies this handoff.

The image is a reused, previously built clean Pi Base with byte-identical
environment inputs. Inspect `image-preparation-attempts.json` for the failed
fresh-build attempt and successful reuse, and `docker-smoke.json` for offline
agent-user source/version/leak checks. Both Harbor trials finished without
exceptions. Positive/negative controls ran through the real Docker grading
entrypoint. Global typecheck has five identical upstream errors on Base and
Oracle.

The additional `challenge.py` can be run from this directory or the repository:
`python3 tasks/pi-context-management/validation/challenge.py /path/to/pi /tmp/fresh-challenge-output`.
It drives the same real CLI with a different batch ordering. Its output directory
must not already contain the `rollover` case directory.
