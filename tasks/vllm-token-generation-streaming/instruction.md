We use the disaggregated token-generation API and the ordinary request works as expected:

```json
{
  "token_ids": [128000, 9906, 11, 1268, 527, 499, 30],
  "sampling_params": {"max_tokens": 20}
}
```

It returns one JSON response after generation finishes. Adding `"stream": true` to the same request does not stream anything; the client still waits for that final JSON object. We need the streaming form to return `text/event-stream` data as tokens become available, for example:

```text
data: {"request_id":"generate-tokens-...","choices":[{"index":0,"logprobs":null,"finish_reason":null,"token_ids":[1102]}],"usage":null}

data: {"request_id":"generate-tokens-...","choices":[{"index":0,"logprobs":null,"finish_reason":"length","token_ids":[6]}],"usage":null}

data: [DONE]
```

Implement streaming for `/inference/v1/generate` without changing its non-streaming response. Preserve choice indexes, token logprobs, finish reasons, and error reporting. Empty token deltas should not create empty data chunks, but an error with no token delta must still be reported. The existing `stream_options` behavior should work here too: `include_usage` adds a final usage-only chunk, `continuous_usage_stats` includes cumulative usage on data chunks, and prompt token details remain available when enabled.
