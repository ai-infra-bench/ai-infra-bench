A customer operating a multi-replica model-serving deployment reports the following problem. Their service runs `MiniMaxAI/MiniMax-M2.5` on two vLLM replicas behind a load balancer. Both replicas use a shared Mooncake store so that long chat prefixes computed by one replica can be reused by the other. Their store configuration at `/etc/vllm/mooncake_store.json` is:

```json
{
  "mode": "embedded",
  "metadata_server": "P2PHANDSHAKE",
  "master_server_address": "10.0.0.10:50051",
  "global_segment_size": "80GB",
  "local_buffer_size": "4GB",
  "protocol": "tcp",
  "device_name": "",
  "enable_offload": false
}
```

The replicas use the same model, tokenizer, block size, hash seed, and connector settings. Apart from their listen ports, they are started with these arguments:

```bash
PYTHONHASHSEED=0 \
MOONCAKE_CONFIG_PATH=/etc/vllm/mooncake_store.json \
vllm serve MiniMaxAI/MiniMax-M2.5 \
  --revision f710177d938eff80b684d42c5aa84b382612f21f \
  --tokenizer-revision f710177d938eff80b684d42c5aa84b382612f21f \
  --trust-remote-code \
  --tensor-parallel-size 4 \
  --max-model-len 4096 \
  --block-size 16 \
  --kv-transfer-config '{"kv_connector":"MooncakeStoreConnector","kv_role":"kv_both","kv_connector_extra_config":{"load_async":true}}' \
  --speculative-config '{"method":"eagle3","model":"thoughtworks/MiniMax-M2.5-Eagle3","revision":"fb4699b3d33913e6b5e2462dd7962775e44e5fea","num_speculative_tokens":3,"draft_tensor_parallel_size":1}'
```

The customer uses the following request body for every trial. Replica A listens on `10.0.0.21:8000` and replica B on `10.0.0.22:8000`.

```json
{
    "model": "MiniMaxAI/MiniMax-M2.5",
    "messages": [
      {
        "role": "system",
        "content": "You maintain a deployment record. When a setting is updated, discard its previous value and answer only from the latest record."
      },
      {
        "role": "user",
        "content": "Initial rollout: region is us-east, replica count is 2, and maximum batch size is 8."
      },
      {
        "role": "assistant",
        "content": "Recorded the initial rollout."
      },
      {
        "role": "user",
        "content": "Production update: region is now us-west, replica count is 4, and maximum batch size is 16. The initial values are superseded."
      },
      {
        "role": "assistant",
        "content": "Recorded the production update."
      },
      {
        "role": "user",
        "content": "Return the current region, replica count, and maximum batch size as one JSON object."
      }
    ],
    "temperature": 0,
    "seed": 0,
    "max_tokens": 80,
    "stream": false
}
```

They expect one JSON object containing `us-west`, `4`, and `16`, with none of the superseded values. Instead, the affected response can combine `us-east` from the initial rollout with the updated replica count, retain the old maximum batch size of `8`, omit one of the updated fields, or put a paraphrase of the system instruction before the JSON object.

The customer reproduces the failure in this order:

1. They start with an empty Mooncake store and send the request to replica A. Replica A has no cached copy, so it computes the whole prompt, returns the expected answer, and stores the prefix blocks in Mooncake.
2. Without clearing Mooncake, they send the identical request to replica B. Replica B has no local copy and loads the prefix written by replica A. The request returns HTTP 200, but its answer shows one or more of the corruptions described above.
3. They start again with an empty Mooncake store and send the request directly to replica B. Its cold answer is correct.
4. They warm the shared prefix again, restart replica B without the `--speculative-config` argument, and resend the request. Its externally loaded answer is also correct.

The vLLM processes remain healthy throughout the comparison. Their serving logs contain no exception, failed transfer, worker restart, or fallback warning. The problem appears only after another replica reuses the externally stored prefix with Eagle-3 enabled.

Investigate and fix this cross-replica warm-response corruption. The same request should preserve the latest conversation state whether its prefix is computed locally or reused from Mooncake. Preserve the working cold-request and non-Eagle paths, as well as other requests that currently load correctly from the shared store.
