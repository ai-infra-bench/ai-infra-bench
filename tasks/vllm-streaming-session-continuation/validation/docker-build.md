# Docker and GPU validation

The pinned Base image builds on A100. The scorer applies the source-only Oracle patch, starts a real vLLM asynchronous engine with a deterministic local GPT-2 model, and runs with network disabled. All three public behavior stages pass with reward 1.
