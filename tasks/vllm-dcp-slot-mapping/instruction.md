I am moving a text-generation deployment from the original GPU model runner to Model Runner V2, and I need to keep using DCP. For example, one of the configurations I want to carry over has these settings:

```json
{
  "tensor_parallel_size": 2,
  "decode_context_parallel_size": 2,
  "cp_kv_cache_interleave_size": 2
}
```

The traffic is ordinary batched generation: a short request may finish while a longer one keeps decoding, and a new prompt can join the next batch. V2 does not yet handle this DCP setup correctly. I use FlashAttention or FlashInfer depending on the deployment. Please make DCP work with their supported paged-KV-cache layouts, in both eager and CUDA-graph execution, so each request keeps producing the correct result as the batch changes and generation crosses cache-block boundaries. Deployments without DCP should continue to work as before.
