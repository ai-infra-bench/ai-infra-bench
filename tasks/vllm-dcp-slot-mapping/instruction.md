I am moving a text-generation deployment from the original GPU model runner to Model Runner V2, and I need to keep using DCP. For example, one of the configurations I want to carry over has these settings:

```json
{
  "tensor_parallel_size": 2,
  "decode_context_parallel_size": 2,
  "cp_kv_cache_interleave_size": 2
}
```

Some of my deployments keep the default KV-cache interleave setting, while others use different settings. I need V2 to handle valid DCP configurations supported by the selected backend and cache block size, not just the example above.

The traffic is ordinary batched generation: a short request may finish while a longer one keeps decoding, and a new prompt can join the next batch. V2 does not yet handle these DCP deployments correctly. I use FlashAttention or FlashInfer depending on the deployment. Please make DCP work with their supported paged-KV-cache layouts, in both eager and CUDA-graph execution, so each request keeps producing the correct result as the batch changes and generation crosses cache-block boundaries. Deployments without DCP should continue to work as before.

I have two GPUs available here and a small random-weight Qwen3 model at `/opt/models/tiny-qwen3` for offline development. It is useful for checking execution and consistency, not language quality.

For FlashAttention graph runs in this image, I use `flash_attn_max_num_splits_for_cuda_graph=1` in the attention configuration. Larger values have a separate startup compatibility problem with the bundled kernel, including on the original runner; fixing that is outside this request.
