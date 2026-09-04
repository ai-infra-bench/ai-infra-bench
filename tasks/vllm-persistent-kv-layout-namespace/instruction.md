We’re gradually moving an inference service from the V1 runner to the V2 runner. The service keeps its KV cache on disk and reuses it after a restart, so repeated inputs do not have to be processed again from scratch.

When V2 starts with an empty cache, it correctly completes “The capital of France is” with an answer beginning with “Paris.” The problem appears during the rollout: we first run V1 and send this request so that it writes to the cache. We then stop V1, start V2 with the same cache directory, and send the request again. The service reports that it reused the cached data, but the generated text is clearly wrong. If we clear the cache directory, V2 works normally again.

Please find the cause and fix the problem. After the fix, V2 should ignore cached data that it cannot safely use. Do not solve the problem by turning off cache reuse: restarting with the same runner should still reuse valid cached data, and cached data that is safe to share should remain shareable.
