An online FP8 quantization job started failing only in its forced-Marlin cases. Loading an OPT-style QKV layer reaches quantization after the final projection weight, then the following projection bias produces a warning about a missing `output_dim` attribute and fails a shape assertion. The same checkpoint order completes with backends that do not rewrite bias during processing, which makes this look backend-specific.

The image includes a deterministic CPU reduction through the production layerwise online-processing lifecycle:

```bash
python /opt/repro/layerwise_bias_trace.py
```

Ensure a layer is not processed until every loadable tensor currently registered on it, including a late-registered bias, has been loaded. Layers without bias, tensors that are intentionally never loaded, delayed finalization, repeated layers, and the existing rule that late bias remains outside meta-device capture must continue to work. Do not disable online processing or defer every layer unconditionally until model loading ends.
