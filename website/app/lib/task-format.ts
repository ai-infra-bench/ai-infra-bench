export function formatLabel(value: string | null) {
  if (!value) return 'Unknown';
  const normalized = value.trim().replace(/[_-]+/g, ' ').replace(/\s+/g, ' ');
  if (/^bug\s*fix$/i.test(normalized)) return 'Bug fix';
  const acronyms: Record<string, string> = {
    ai: 'AI', api: 'API', asr: 'ASR', cpu: 'CPU', gpu: 'GPU', kv: 'KV',
    e2e: 'e2e', rpc: 'RPC', http: 'HTTP', sdk: 'SDK', os: 'OS',
  };
  return normalized.split(' ').map((word, index) => {
    const lower = word.toLowerCase();
    return acronyms[lower] ?? (index === 0 ? lower.charAt(0).toUpperCase() + lower.slice(1) : lower);
  }).join(' ');
}

export function formatTaskTitle(slug: string) {
  const spellings: Record<string, string> = {
    api: 'API',
    asr: 'ASR',
    cpu: 'CPU',
    eagle: 'Eagle',
    kv: 'KV',
    m3: 'M3',
    minimax: 'MiniMax',
    mooncake: 'Mooncake',
    pyav: 'PyAV',
    ray: 'Ray',
    vllm: 'vLLM',
  };

  return slug
    .replace(/^vllm-/, '')
    .split('-')
    .map((part) => spellings[part] ?? part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

export function formatProjectName(repository: string | null) {
  if (!repository) return 'Unknown project';

  const normalized = repository.toLowerCase();
  if (normalized === 'vllm-project/vllm') return 'vLLM';
  if (normalized.includes('sglang')) return 'SGLang';
  if (normalized.includes('tensorrt-llm')) return 'TensorRT-LLM';

  return repository.split('/').at(-1) ?? repository;
}
