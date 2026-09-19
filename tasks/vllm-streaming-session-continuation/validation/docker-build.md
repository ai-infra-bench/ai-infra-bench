# Docker and GPU validation

This revision reuses image `sha256:7089f7eb9e06fff0a086aa0c8ad919aa20fc5f1ec6911a954e81e3316f35846e`; no environment build inputs or agent-visible interface scaffolding were changed. The source-only reference patch and every control apply to its exact Base. Each real-model evaluation uses one A100, with network disabled, a fresh small model and one persistent engine for the behavior scenarios.

The model, tokenizer and expected outputs are generated at verification time. Expected outputs are calculated independently in the trusted parent. Candidate-controlled results never supply expected values. The native donor remains the historical ABI approximation described in `environment/lock/README.md`.

The local Harbor adapter in `harbor_gpu.py` supplies explicit GPU allocation and Docker network isolation for the offline task. Exact image identity, executable hashes, rewards and measured durations belong to `e2e-evidence.json` and `local-regressions.json`.
