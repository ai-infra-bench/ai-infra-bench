I am an infrastructure engineer investigating a serving-performance regression in a vLLM deployment. Chunked prefill is enabled, and the affected traffic includes bursts of long prompts arriving while other requests are already generating tokens.

During the investigation, I found that under high KV-cache pressure, some long requests are repeatedly preempted after partial prefill and lose the progress they made. They return to the queue, are admitted again, and repeat the same cycle. While this continues, requests that were already decoding can go for extended periods without producing new tokens.

I need you to fix the scheduling behavior so this finite mixed workload makes steady progress. The scheduler may still preempt requests when necessary, but it must not repeatedly admit and preempt the same request without durable progress. Active generations and queued long prompts must both complete.

Do not solve this by delaying every new prompt until all active generations have finished. Requests that the current scheduler can run concurrently must retain that behavior, including requests that reuse cached prefixes and long prompts on sliding-window or chunked-local-attention models.
