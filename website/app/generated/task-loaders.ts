export const taskLoaders = {
  "vllm-anthropic-inline-system-template": () => import('./task-details/vllm-anthropic-inline-system-template.json'),
  "vllm-asr-chunk-spacing": () => import('./task-details/vllm-asr-chunk-spacing.json'),
  "vllm-async-kv-token-accounting": () => import('./task-details/vllm-async-kv-token-accounting.json'),
  "vllm-async-spec-placeholder-discard": () => import('./task-details/vllm-async-spec-placeholder-discard.json'),
  "vllm-concurrent-config-refresh": () => import('./task-details/vllm-concurrent-config-refresh.json'),
  "vllm-cpu-offload-reset-inflight": () => import('./task-details/vllm-cpu-offload-reset-inflight.json'),
  "vllm-kv-admission-thrashing": () => import('./task-details/vllm-kv-admission-thrashing.json'),
  "vllm-minimax-m3-streaming-reasoning": () => import('./task-details/vllm-minimax-m3-streaming-reasoning.json'),
  "vllm-mooncake-eagle-load-mask": () => import('./task-details/vllm-mooncake-eagle-load-mask.json'),
  "vllm-persistent-kv-layout-namespace": () => import('./task-details/vllm-persistent-kv-layout-namespace.json'),
  "vllm-pyav-target-frame-selection": () => import('./task-details/vllm-pyav-target-frame-selection.json'),
  "vllm-ray-zero-copy-logprobs": () => import('./task-details/vllm-ray-zero-copy-logprobs.json'),
} as const;
