We use the persistent filesystem KV-offload tier so cached prefixes survive worker restarts. With OPT-125M in FP16 at TP=PP=1, a cold V2 runner completes “The capital of France is” with “Paris…”. If the same cache root is first populated by a V1 runner and the service is then restarted with the V2 runner, the request reports a persistent-cache hit but the greedy continuation becomes `.,,,,,, the the.,,,, by a`. Deleting the cache root restores the correct result.

The persisted block files from both runs have the same byte size, so the existing size and single-rank configuration checks accept them. The failure only appears when the second runner reuses files written by the other runner; cold V1 and cold V2 runs are individually stable.

The cache may persist across restarts, but a runner must not treat files from an incompatible layout as valid hits. Configurations whose stored layout is genuinely portable across parallel settings must still be able to share the same persistent data.
