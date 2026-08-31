While validating an asynchronous KV connector, I captured the following scheduler state for a 70-token request:

```text
connector result: matched_tokens=37, load_kv_async=True
request state after scheduling: WAITING_FOR_REMOTE_KVS
runner input after transfer completion: num_computed_tokens=48
tokens scheduled after transfer completion: 22
```

Where are the extra cached tokens coming from between the connector result and the runner input? Fix this so the two sides agree on how much of the request has already been computed, while behavior that already works correctly stays unchanged.
