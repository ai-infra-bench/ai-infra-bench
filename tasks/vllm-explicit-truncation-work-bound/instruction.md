Requests that explicitly set both `truncate_prompt_tokens` and `truncation_side` return the requested token slice, but very large text inputs still make preprocessing work over the complete prompt before that slice is applied. The same renderer already bounds tokenizer work in other length-checking branches, so this configuration unexpectedly loses the resource bound it appears to request.

The image contains a deterministic CPU reproduction through the production `HfRenderer` prompt pipeline:

```bash
python /opt/repro/explicit_truncation_trace.py
```

Ensure tokenizer work is bounded by the available input context when explicit-side truncation is active, while preserving which end of the prompt the caller requested. Left and right truncation, different tokenizer character-to-token bounds, async and sync rendering, no-truncation validation, tokenizer-default truncation, token-list inputs, lower-casing, special-token options, and configurations without a context limit must retain their current behavior. Do not merely change the final token slice after the tokenizer has already processed the full text.
