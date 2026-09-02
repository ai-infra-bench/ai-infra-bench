I have a prompt gateway app in `/workspace/prompt-gateway`. It starts a vLLM runtime in a Ray actor, reads queued requests, checks their token budgets, and groups them into batches. The vLLM checkout is in `/workspace/vllm`.

Running it currently fails:

```text
2026-09-02 15:37:43 INFO prompt_gateway starting prompt gateway with config /workspace/prompt-gateway/settings.json
2026-09-02 15:37:45 INFO worker.py Started a local Ray instance.
2026-09-02 15:38:10 INFO prompt_gateway loaded 3 requests from /workspace/prompt-gateway/requests.jsonl
2026-09-02 15:38:13 ERROR prompt_gateway prompt gateway failed while preparing the next request batch
Traceback (most recent call last):
  File "/workspace/prompt-gateway/main.py", line 87, in run
    report = self._plan(tokenizer, requests)
  File "/workspace/prompt-gateway/main.py", line 69, in _plan
    return ray.get(future)
  File "/usr/local/lib/python3.12/site-packages/ray/_private/worker.py", line 2980, in get
    values, debugger_breakpoint = worker.get_objects(
  File "/usr/local/lib/python3.12/site-packages/ray/_private/worker.py", line 1023, in get_objects
    raise value.as_instanceof_cause()
ray.exceptions.RayTaskError(AttributeError): ray::plan_remote_batch()
  File "/workspace/prompt-gateway/pipeline.py", line 152, in plan_remote_batch
    report = AdmissionPipeline(tokenizer, settings).run(requests)
  File "/workspace/prompt-gateway/pipeline.py", line 109, in run
    inspected = self._inspector.inspect(request)
  File "/workspace/prompt-gateway/pipeline.py", line 35, in inspect
    token_ids = self._tokenizer.encode(request.prompt)
  File "/workspace/prompt-gateway/pipeline.py", line 25, in encode
    token_ids = self._tokenizer.encode(prompt, add_special_tokens=False)
AttributeError: 'NoneType' object has no attribute 'encode'
```

This looks like a vLLM problem rather than a malformed request. Find the cause and fix it in `/workspace/vllm`. Existing local and concurrent tokenizer use should keep working.
