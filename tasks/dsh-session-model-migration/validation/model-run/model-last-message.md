**Implemented**
- Added opt-in `migration: "checked"` with typed rejection reasons in `packages/api/session-controller/src/types.ts:181`.
- Added atomic idle/pending-state checks, destination capacity estimation, output-default replacement, and durable session-local selection in `packages/api/session-controller/src/commands.ts:160`.
- Added `responsesReasoningText` validation and cross-route Responses reasoning replay while preserving native same-route fidelity in `packages/llm/llm-pi-ai/src/config.ts:151` and `packages/llm/llm-pi-ai/src/replay.ts:264`.
- Added end-to-end lifecycle coverage for migration, rejection, reopening, retained tool history, and continued tool execution in `packages/api/session-controller/tests/checked-migration.host.spec.ts:167`.
- Updated bilingual package/subsystem docs, generated catalogs/graphs, and the architecture note at `.agents/notes/implemented/architecture/2026-09-10-checked-session-model-migration.md:1`.

**Validation**
- 148 focused migration/pi-ai tests passed; 14 legacy model-selection tests passed.
- Host build, host/client typechecks, full lint, translation pairing, documentation graph, README, wrapping, budget, and whitespace checks passed.

