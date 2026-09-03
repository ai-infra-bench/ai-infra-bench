I’m using `MiniMaxAI/MiniMax-M3-MXFP8` behind vLLM’s OpenAI-compatible chat completions API. Our incident-response service exposes a runbook search function:

```json
{
  "model": "MiniMaxAI/MiniMax-M3-MXFP8",
  "messages": [
    {
      "role": "user",
      "content": "Checkout API is returning elevated 502s. Search the current incident runbooks for mitigation steps before answering."
    }
  ],
  "stream": true,
  "tool_choice": "auto",
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "search_incident_runbooks",
        "parameters": {
          "type": "object",
          "properties": {
            "service": {"type": "string"},
            "symptom": {"type": "string"}
          },
          "required": ["service", "symptom"]
        }
      }
    }
  ]
}
```

With the default adaptive thinking mode, reasoning and its markers are emitted as normal content before the structured function call:

```text
data: {"choices":[{"delta":{"reasoning":null,"content":"<mm:think>"}}]}
data: {"choices":[{"delta":{"reasoning":null,"content":"I should search the current checkout incident runbook first."}}]}
data: {"choices":[{"delta":{"reasoning":null,"content":"</mm:think>"}}]}
data: {"choices":[{"delta":{"reasoning":null,"content":null,"tool_calls":[{"type":"function","function":{"name":"search_incident_runbooks","arguments":"{\"service\":\"checkout-api\",\"symptom\":\"elevated 502s\"}"}}]}}]}
```

I also tried the same request with:

```json
"chat_template_kwargs": {"thinking_mode": "enabled"}
```

That stream starts in the reasoning field, but it never transitions to the structured function call:

```text
data: {"choices":[{"delta":{"reasoning":"I should search the current checkout incident runbook first."}}]}
data: {"choices":[{"delta":{"reasoning":"</mm:think>"}}]}
data: {"choices":[{"delta":{"reasoning":"]<]minimax[>[<tool_call>\n]<]minimax[>[<invoke name=\"search_incident_runbooks\">]<]minimax[>[<service>checkout-api]<]minimax[>[</service>]<]minimax[>[<symptom>elevated 502s]<]minimax[>[</symptom>]<]minimax[>[</invoke>\n]<]minimax[>[</tool_call>"},"finish_reason":"stop"}]}
```

For both modes, sending the same request with `"stream":false` returns clean reasoning, hides the `<mm:think>` markers, and returns the structured `search_incident_runbooks` call with the expected arguments.

Fix both streaming failures so adaptive and enabled thinking separate reasoning, visible content, and structured function calls in the same way as the working non-streaming requests. Preserve existing disabled-thinking, atomic-marker, and plain-text streaming behavior. Text that only resembles an incomplete marker, such as ordinary content ending in `<` or `<mm:`, must not disappear.
