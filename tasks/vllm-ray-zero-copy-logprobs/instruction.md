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

I cannot reproduce this on a single node, so something about the multi-node path is leaving the service unhealthy after an otherwise successful response. I need the two-node deployment to keep serving requests normally without changing completion results or returned log probabilities.
