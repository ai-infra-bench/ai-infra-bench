Let vLLM choose the model runner when `VLLM_USE_V2_MODEL_RUNNER` is unset. For this initial rollout, default to V2 only for supported dense, unquantized Qwen3 text-generation configurations. Leave other configurations on V1.

Keep the explicit overrides: `0` forces V1, and `1` requests V2, including compatible models outside the automatic rollout. Base the choice on what the current V2 runner supports. In auto mode, leave unsupported configurations on V1; if `1` is explicitly set, fail startup with a clear error. There’s no need to add support for new features in V2.

Make sure the engine worker actually starts with the selected runner, rather than making a conflicting choice from the environment default.
