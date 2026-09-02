We run a multi-tenant vLLM service with runtime LoRA updating enabled. Two requests can be decoding with adapters A and B while another tenant loads adapters C and D through the live adapter-loading API. With two active LoRA slots, the in-flight requests sometimes continue without an error but start producing output influenced by the other adapter. Repeating the same decodes without hot-loading is stable.

The attached CPU reproduction reduces the incident to the production LoRA manager and its token-to-slot routing:

```bash
python /opt/repro/lora_hotload_trace.py
```

After a full-slot eviction and restoration of the original batch, each token must still resolve to its requested adapter. Repeated mapping calls without a slot change should retain their current behavior, mapping changes must continue to work, and adapter activation, eviction, registration, and ordinary single-adapter routing must remain compatible.

Fix the LoRA manager so a live adapter hot-load cannot silently route an in-flight request through another adapter's weights. Do not disable runtime loading or avoid slot reuse.
