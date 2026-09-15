# Behavior to verification map

All paths below are relative to tasks/dsh-session-model-migration/tests. Assertions were read with their fixtures and scoring entrypoint. This map separates observed coverage from completeness claims.

| Contract | Component tests | Real-process observation | Review result |
|---|---|---|---|
| Checked selection; legacy selection unchanged | budget legacy selection and checked migration | Remote session/selectModel; cold adoption | Both entry paths exercised |
| Destination estimate includes retained work, latest prompt/tools, reserved output; exact fit allowed | budget exact-fit and explicit allowance | main/reject with actual CLI, tools and HTTP | High source usage vs destination re-estimate was missing; independent probe added in isolation |
| Both capacities known; no invented request default | UnknownCatalog negative cases; capacity-reopen catalog cases | Default and caller allowance cases | Unknown adapter is a valid metadata boundary substitute; catalog fixture still binds a private helper |
| Caller allowance persists, defaults follow destination | capacity-reopen (nonempty, empty, consecutive migrations) | empty-same, empty-third, defaults, main | Actual source requests, persisted events and destination request fields observed |
| Idle/no pending work; reject changes during check | budget queued input, real blocked stream, delayed real adapter lookup plus enqueue/clear | rejection preserves old route | Causal gates; observers do not release before the checked rejection |
| No generation during admission | endpoint request counts across budget/migration/collision | request-count checks around select | Actual HTTP observed |
| Rejection leaves selection/history usable | event snapshots plus subsequent source turn | reject with restart | Nonempty error required without fixed wording |
| Success is session-local and survives reopening | sibling selection, settings bytes, saved-event replay | first Host stops; second Host public cold adoption with no seed or maxTokens; sibling unchanged | Genuine independent process and disk lifecycle |
| Responses/Chat options boolean, protocol-specific, disabled by default | config and inherited catalog cases; disabled replay cases | real profile Loader and native Chat continuation | Old private config validation assertion already repaired in v0.0.8; not a new finding |
| Plaintext reasoning association/order and reasoning-only history | migration, replay, chat-reasoning | main/chat-* assert actual gateway request before responding | Source protocol x destination protocol x reopen combination strengthened by independent Responses-to-Chat probe |
| Parallel/provider-specific call IDs preserve pairing | collision six dimensions and source tool results | two real bash calls, strict HTTP pairing and report artifact | No exact destination ID spelling required; source is a custom compatible gateway and IDs are strings at the frozen SDK boundary |
| Foreign native metadata discarded; same-route retained | replay native/foreign metadata; native follow-up | main native call/item ID; chat native reasoning | Independent return-to-source probe strengthens interaction coverage |
| Do not fabricate reasoning or rewrite saved history | unavailable reasoning and complete saved prefix checks | independent full-frame Zstd decode before/after restart | Observer reads files; never supplies restored state to second Host |
| All required checks complete; candidate cannot self-report reward | grade.py exact case inventory, root report/worker split | root provider/assertion owner; nobody candidate Host | Existing early-exit/forged-report controls remain historical evidence; no claim of universal sandbox security |

The unit suite is itself integration-heavy: real Loader, sessions, SDK, token meter and agent loop. The separate process layer adds CLI/Remote, actual bash, disk persistence and cold recovery. Deterministic SSE controls generation, not migration or replay logic. No GPU/model forward pass determines the target transition.

No statement expansion is proposed. New tests must be justified by existing clauses and cannot define private helper names, hashes or an Oracle-specific ID mapping algorithm.
