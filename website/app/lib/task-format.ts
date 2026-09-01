export function formatLabel(value: string | null) {
  if (!value) return 'Unknown';
  return value
    .replaceAll('_', ' ')
    .replaceAll('-', ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
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
