# Public interface bindings

The prompt intentionally leaves new tool names, schemas, addresses and transports open.
These curator-owned adapters translate documented public calls and model-visible receipts;
they neither load candidate adapter code nor implement delivery, wait for replies, inject
messages into recipient context, or change the submitted patch.

| Submission | Public interface mapping |
|---|---|
| G6 #1 | `team_members`, `team_send(to,text)`, `*` for broadcast; structured receipts |
| G6 #2 | Generated `worker-N` IDs mapped to scenario roles; `workers` roster; `team_send(to,text)`, `*` broadcast; explicit error text parsed |
| G6 #3 | Generated `worker-N` IDs; `team_members`, `team_send(to,text)`, separate `team_broadcast`; explicit `kind:error` recognized |
| G6 #4 | Optional task IDs; `team_list`, `team_send(to,text)`, `team_broadcast`; failed `to` field renamed |
| G56 #1 | Optional task IDs; `team_list`, `team_send(recipient,message)`, `team_broadcast`; structured self and delivery receipts |
| G56 #2 | Optional task IDs; same tool names as #1; JSON roster and human-readable acceptance/rejection text |
| G56 #4 | Optional task IDs; `subagent_teammates`, `subagent_send(recipient,message)`, `subagent_broadcast`; human-readable roster/receipts |

G56 #2's public self-send rejection says “cannot send a message to yourself” without
repeating the address. The adapter keeps the submitted recipient for this explicit error
only. Unknown/finished addresses are parsed directly from returned error text. It never
infers acceptance from the request. The malformed-input probes use missing/wrong-type
recipients and empty/wrong-type messages, avoiding an artificial requirement for mutually
exclusive broadcast fields when broadcast is a separate tool.

G6 #3's first binding omitted recognition of the returned `kind:error` object; it was
corrected before final scoring. Both the original grade and original binding are archived
under `*-before-error-mapping` in the artifact root. The candidate patch is unchanged.

For every sample, the frozen binding and candidate hashes are recorded alongside the
scorer hashes in `pass4-results.json`; the completed sample was graded only after reviewing
its public tool registration, schemas and result formatting. This review establishes
interface compatibility, not a claim that every source-code path was independently audited.
