# Oracle: agent-trace extension

`solve.sh` applies `oracle.patch` to the pinned Pi checkout. It adds the tracing
extension, its README and offline tests without changing Pi core or existing tests.

The tracer writes one live start and one completed OTLP/JSON record per run,
turn, provider request, tool and compaction. Session entry ids come from the
persisted branch. Reload/resume retain the session trace id; shutdown closes
open spans, and write failures produce one context-only report.

Spawning tools cooperate via the documented `agent-trace:child-env` event on
`pi.events`: supply the active `toolCallId` and receive a copied environment in
`reply`. The tracer looks up that specific tool span and never mutates the
parent process environment. Sibling tools can spawn concurrently without
stealing each other's parent. Child runs and compactions inherit that parent;
nonparticipating tools still have spans but no automatic child attribution.

User and custom continuation messages are resolved by the first message role
actually consumed by the run. Failed/aborted assistant responses lacking an
`errorMessage` use `aborted` for both chat and turn status.

The added offline tests exercise real AgentSession scheduling and persistence
with the faux provider: trace encoding/tree, user continuation, missing error
message and overlapping tools requesting isolated environments. Verifier
cross-process tests remain independent of the Oracle's choice of event name.
