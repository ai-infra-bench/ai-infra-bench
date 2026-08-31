Our monitoring pipeline records the selected tokens' log probabilities and samples unusually low-likelihood completions for developers to debug. The vLLM service runs on a two-node Ray cluster with one GPU per node, TP set to 1, PP set to 2.

One completion request returns HTTP 200 with both text and logprobs:

```python
import requests

response = requests.post(
    "http://localhost:8000/v1/completions",
    json={
        "prompt": "Summarize this customer-support ticket in one sentence: The app closes whenever I upload a photo.",
        "max_tokens": 24,
        "logprobs": 0,
    },
)
print(response.json())
```

Around 30 seconds after the successful response, EngineCore exits with:

```text
ray.exceptions.RayChannelTimeoutError: System error: Timed out acquiring the read lock.
vllm.v1.engine.exceptions.EngineDeadError: EngineCore encountered an issue.
```

I tried to debug the problem in a single-node Ray setup, but could not reproduce it there. Fix the multi-node crash so the service remains healthy and its existing completion behavior, including returned log probabilities, continues to work normally.
