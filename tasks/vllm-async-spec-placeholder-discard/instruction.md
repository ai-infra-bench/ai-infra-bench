We run a Qwen3-0.6B completion service with asynchronous scheduling and ngram speculative decoding. During an RLHF evaluation loop, 24 concurrent requests generate long completions while the control plane calls `/reset_prefix_cache?reset_running_requests=true` after each weight refresh.

The reset endpoint reports success, but scheduler instrumentation sometimes records a negative output-placeholder count immediately afterward. In one 100-second run with 11 resets, this happened 9 times; a representative event had `num_output_placeholders=-4` while stale async output was still pending. Once that invalid state reaches a normal output update, `assert request.num_output_placeholders >= 0` can terminate EngineCore.

Investigate and fix this reset-related accounting failure. Repeated resets must not leave resumed requests with invalid counters or stop forward progress, and speculative decoding without a reset must keep its existing acceptance and rejection behavior.
