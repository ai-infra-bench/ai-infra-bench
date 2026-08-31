I am using vLLM's Anthropic API. The server is running Qwen3.6-27B, and this request fails:

```python
import anthropic

client = anthropic.Anthropic(
    api_key="test",
    base_url="http://localhost:8000",
)

messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Please check the GPU status for vLLM."},
    {"role": "assistant", "content": "Sure, I will check it."},
    {"role": "user", "content": "Show me the nvidia-smi output."},
    {"role": "assistant", "content": "The GPU status looks normal, with utilization around 15%."},
    {"role": "user", "content": "Write up the results as a report."},
    {"role": "system", "content": "Task instruction: Based on the conversation above, generate a brief GPU status report."},
    {"role": "user", "content": "Please summarize the above."},
]

client.messages.create(
    model="Qwen3.6-27B",
    max_tokens=512,
    messages=messages,
)
```

The SDK receives HTTP 500 from vLLM with this response:

```
System message must be at the beginning.
```

The conversation already begins with a system message, so this response does not make sense to me. Can you fix the messages and token-counting endpoints to handle this request correctly?
