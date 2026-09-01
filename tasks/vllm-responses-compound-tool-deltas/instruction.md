We are using Kimi K2.5 through the streaming /v1/responses API for an agent that writes generated files. The request succeeds with HTTP 200, but some completed function calls contain invalid JSON even though the model selected the right tool. The same deployment does not show the problem on every request, and ordinary text streaming is working.

Here is one request from the affected workload:

```json
{
  "model": "moonshotai/Kimi-K2.5",
  "stream": true,
  "reasoning": {"effort": "low"},
  "input": "Call the write tool to put print(\"hi\") into /tmp/x.py. No explanation.",
  "tools": [
    {
      "type": "function",
      "name": "write",
      "description": "Write content to a file at the given path.",
      "parameters": {
        "type": "object",
        "properties": {
          "path": {"type": "string"},
          "content": {"type": "string"}
        },
        "required": ["path", "content"]
      }
    }
  ]
}
```

In this captured batch, only one of ten response.function_call_arguments.done values parsed successfully. A broken stream started like this:

```text
POST /v1/responses 200
response.output_item.added                     name="write"
response.function_call_arguments.delta         "/x.py\", \""
response.function_call_arguments.delta         "content\": \"print"
response.function_call_arguments.delta         "(\\\"hi\\\")\"}"
response.function_call_arguments.done          "/x.py\", \"content\": \"print(\\\"hi\\\")\"}"
json.loads(done.arguments) -> JSONDecodeError
```

The exact failure rate changes with model decode chunking. A stream may deliver assistant text, reasoning, a tool name, the first argument bytes, or updates for more than one tool together. Each typed SSE event must retain the original order and bytes, and every completed tool item must contain the arguments for that tool only. Correct the streaming behavior without changing valid plain-text, reasoning-only, separate-delta, or non-streaming responses. The Kimi model weights are not included in this CPU image.
