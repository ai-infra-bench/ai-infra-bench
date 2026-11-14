I am using vLLM's Cohere v2 API with tool calling enabled. Requests that set
`tool_choice` to `"REQUIRED"` are currently accepted even when `tools` is
omitted, null, or an empty list. Such requests cannot satisfy the requested
tool choice and continue into downstream request handling.

Update both `POST /cohere/v2/chat` and `POST /cohere/v2/chat/render` so these
invalid requests return HTTP 400 before either endpoint invokes its downstream
handler. The response must use the Cohere error envelope: a JSON object with a
non-empty `message` that explains that `REQUIRED` needs tools, not vLLM's
internal `error` envelope.

Preserve valid Cohere v2 behavior. A `"REQUIRED"` request with at least one
tool must still be accepted, and requests with `tool_choice` omitted or set to
`"NONE"` must continue to allow omitted, null, or empty `tools`.
