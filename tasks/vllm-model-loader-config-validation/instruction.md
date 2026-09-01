`DefaultModelLoader` and `LoadConfig` accept several invalid profiles, but the actual load either fails much later with an unrelated internal exception or starts after silently ignoring part of the requested configuration.

These are the cases I can reproduce:

| Configuration | Current result |
| --- | --- |
| load_format is a non-string Python value | construction succeeds, then code using the format raises an AttributeError |
| safetensors_load_strategy has a typo | the typo is accepted and loading behaves like the default lazy strategy |
| model_loader_extra_config is not a mapping | loader construction fails while trying to read mapping keys |
| enable_multithread_load is not a boolean | the value is accepted and later interpreted by truthiness |
| multithread loading has num_threads=0 | startup reaches ThreadPoolExecutor and reports that max_workers must be greater than 0 |
| multithread loading is combined with eager, prefetch, or torchao | the model loads, but the selected safetensors strategy is ignored |
| load_format="safetensors" points at a directory containing only model.pt | the .pt file is opened as safetensors and produces a SafetensorError about its header |

Invalid profiles should be rejected when the load configuration or loader is constructed, with an error that identifies the bad field. An explicit safetensors format must not fall back to PyTorch files, while auto and hf loading must keep their existing PyTorch fallback. Custom string load formats, valid thread counts, single-thread strategies, ordinary pt loading, and the existing unknown-extra-key rejection must continue to work.
