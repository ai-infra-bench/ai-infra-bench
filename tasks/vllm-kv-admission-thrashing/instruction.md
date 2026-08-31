I am seeing a severe throughput drop while serving a workload with long prompts. Chunked prefill is enabled, and the same request repeatedly reports that it was preempted without making visible progress.

The logs contain repeated entries like these:

    (EngineCore_DP0 pid=11842) WARNING 03-17 15:39:29 [scheduler.py:928] Request cmpl-bench-5f83f700-51-0-bfc32831 preempted (num_tokens=40000, computed_tokens=32568, preemption_count=7) due to insufficient KV cache blocks.
    (EngineCore_DP0 pid=11842) WARNING 03-17 15:39:30 [scheduler.py:928] Request cmpl-bench-5f83f700-51-0-bfc32831 preempted (num_tokens=40000, computed_tokens=32568, preemption_count=8) due to insufficient KV cache blocks.
    (EngineCore_DP0 pid=11842) WARNING 03-17 15:39:32 [scheduler.py:928] Request cmpl-bench-5f83f700-51-0-bfc32831 preempted (num_tokens=40000, computed_tokens=32568, preemption_count=9) due to insufficient KV cache blocks.

The requests that are already decoding slow down badly whenever this happens. Trace why the long request keeps returning to the same preempted state without making progress, and fix the scheduler.
