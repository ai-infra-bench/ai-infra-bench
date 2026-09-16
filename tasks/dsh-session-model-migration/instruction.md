# Continue an existing session on another model

We want to continue existing DeepSeek Harness sessions on another provider or model without losing work. Smaller models may not fit the conversation, while our Chat Completions and Responses gateways need the plaintext reasoning associated with historical tool calls to resume the conversation.

Add an opt-in `migration: "checked"` mode to the Session Controller's `selectModel` operation. It should check whether the destination can carry the session's current work before committing the change. Existing requests without this option must keep their behavior.

Use Harness’s token-meter estimate, repriced for the destination, to check that retained conversation, the latest request’s system prompt and tool schemas, and reserved output together fit the destination’s context window. The destination’s context window and maximum output capacity must both be known. Preserve a caller-selected output allowance; otherwise use the destination’s request default, or reserve its maximum output capacity if it has no request default. Reject an allowance above that capacity or a total above the context window; do not reduce the allowance or discard work to fit.

Caller-selected allowances must survive migration and reopening, including before the first request. Adapter defaults follow the destination and must not become caller selections; reserving capacity must not invent a request default. Apply admission to empty sessions with zero history overhead and to already-selected routes.

Check only idle sessions with no pending input; reject migration if the session changes during the check. Checks must not make provider generation requests. Rejections should explain the problem and leave the original selection and history usable and unchanged, without recording a selection. Successful changes must survive reopening from saved events and preserve messages, tool results, and provenance. Migration affects only this session, leaving other sessions and the deployment default unchanged. Admission covers the retained work at selection time.

For the gateway, add a boolean `responsesReasoningText` option to `llm-pi-ai` provider profiles, defaulting to false; reject enabling it outside `openai-responses` routes. The gateway accepts plaintext reasoning as `{ "type": "reasoning", "content": [{ "type": "reasoning_text", "text": "..." }] }`.

Also support a boolean `chatReasoningText` option, defaulting to false and allowed only on `openai-completions` routes. These gateways accept plaintext reasoning in the original assistant message's `reasoning_content` field, alongside its text and tool calls. Preserve available reasoning on assistant messages without tool calls as well.

When the applicable option is enabled, carry available plaintext reasoning after provider or model changes in the target gateway's reasoning format, preserving its association and order with assistant text and calls. Keep calls and results correctly paired, including parallel calls and provider-specific IDs. Other routes' opaque reasoning, response/item IDs, and signatures must not become destination-native state. Do not fabricate missing reasoning or rewrite stored history. Keep same-route native replay intact, and preserve existing serialization when the option is disabled.

Include integration coverage for continuing tool-using sessions with new tool calls and results after migration or reopening, and for rejection. Update public types, configuration validation, and documentation.
