import { mkdir, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';

const projectDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const outputDir = path.join(projectDir, 'public', 'logos', 'ai-infra');
const cardOutputDir = path.join(outputDir, 'card');
const appManifestFile = path.join(projectDir, 'app', 'generated', 'repository-logos.json');

const repositories = [
  { name: 'vLLM', repo: 'vllm-project/vllm', category: 'serving-runtime', tier: 'core' },
  { name: 'SGLang', repo: 'sgl-project/sglang', category: 'serving-runtime', tier: 'core' },
  { name: 'TensorRT-LLM', repo: 'NVIDIA/TensorRT-LLM', category: 'serving-runtime', tier: 'core' },
  { name: 'Text Generation Inference', repo: 'huggingface/text-generation-inference', category: 'serving-runtime', tier: 'core', status: 'archived' },
  { name: 'LMDeploy', repo: 'InternLM/lmdeploy', category: 'serving-runtime', tier: 'core' },
  { name: 'llama.cpp', repo: 'ggml-org/llama.cpp', category: 'serving-runtime', tier: 'core' },
  { name: 'MLC LLM', repo: 'mlc-ai/mlc-llm', category: 'serving-runtime', tier: 'core' },
  { name: 'NVIDIA Dynamo', repo: 'ai-dynamo/dynamo', category: 'serving-runtime', tier: 'core' },
  { name: 'llm-d', repo: 'llm-d/llm-d', category: 'serving-runtime', tier: 'core' },
  { name: 'DeepSpeed-MII', repo: 'deepspeedai/DeepSpeed-MII', category: 'serving-runtime', tier: 'core' },
  { name: 'LightLLM', repo: 'ModelTC/LightLLM', category: 'serving-runtime', tier: 'core' },
  { name: 'ONNX Runtime', repo: 'microsoft/onnxruntime', category: 'serving-runtime', tier: 'extended' },
  { name: 'OpenVINO', repo: 'openvinotoolkit/openvino', category: 'serving-runtime', tier: 'extended' },
  { name: 'TensorRT', repo: 'NVIDIA/TensorRT', category: 'serving-runtime', tier: 'extended' },
  { name: 'xFasterTransformer', repo: 'intel/xFasterTransformer', category: 'serving-runtime', tier: 'extended' },
  { name: 'Mistral Inference', repo: 'mistralai/mistral-inference', category: 'serving-runtime', tier: 'extended', status: 'archived' },
  { name: 'FasterTransformer', repo: 'NVIDIA/FasterTransformer', category: 'serving-runtime', tier: 'extended', status: 'legacy' },

  { name: 'Triton', repo: 'triton-lang/triton', category: 'kernel-compiler', tier: 'core' },
  { name: 'TileLang', repo: 'tile-ai/tilelang', category: 'kernel-compiler', tier: 'core' },
  { name: 'FlashInfer', repo: 'flashinfer-ai/flashinfer', category: 'kernel-compiler', tier: 'core' },
  { name: 'FlashAttention', repo: 'Dao-AILab/flash-attention', category: 'kernel-compiler', tier: 'core' },
  { name: 'CUTLASS', repo: 'NVIDIA/cutlass', category: 'kernel-compiler', tier: 'core' },
  { name: 'xFormers', repo: 'facebookresearch/xformers', category: 'kernel-compiler', tier: 'core' },
  { name: 'Transformer Engine', repo: 'NVIDIA/TransformerEngine', category: 'kernel-compiler', tier: 'core' },
  { name: 'AITER', repo: 'ROCm/aiter', category: 'kernel-compiler', tier: 'core' },
  { name: 'TVM', repo: 'apache/tvm', category: 'kernel-compiler', tier: 'extended' },
  { name: 'XLA', repo: 'openxla/xla', category: 'kernel-compiler', tier: 'extended' },
  { name: 'Marlin', repo: 'IST-DASLab/marlin', category: 'kernel-compiler', tier: 'extended' },
  { name: 'AWQ', repo: 'mit-han-lab/llm-awq', category: 'kernel-compiler', tier: 'extended' },
  { name: 'GPTQ', repo: 'IST-DASLab/gptq', category: 'kernel-compiler', tier: 'extended' },
  { name: 'torchao', repo: 'pytorch/ao', category: 'kernel-compiler', tier: 'extended' },
  { name: 'LLM Compressor', repo: 'vllm-project/llm-compressor', category: 'kernel-compiler', tier: 'extended' },

  { name: 'Mooncake', repo: 'kvcache-ai/Mooncake', category: 'cache-distributed', tier: 'core' },
  { name: 'LMCache', repo: 'LMCache/LMCache', category: 'cache-distributed', tier: 'core' },
  { name: 'kvcached', repo: 'ovg-project/kvcached', category: 'cache-distributed', tier: 'core' },
  { name: 'FlexKV', repo: 'taco-project/FlexKV', category: 'cache-distributed', tier: 'core' },
  { name: 'llm-d KV Cache', repo: 'llm-d/llm-d-kv-cache', category: 'cache-distributed', tier: 'core' },
  { name: 'KVPress', repo: 'NVIDIA/kvpress', category: 'cache-distributed', tier: 'extended' },
  { name: 'Ray', repo: 'ray-project/ray', category: 'cache-distributed', tier: 'core' },
  { name: 'NCCL', repo: 'NVIDIA/nccl', category: 'cache-distributed', tier: 'core' },

  { name: 'PyTorch', repo: 'pytorch/pytorch', category: 'framework-tooling', tier: 'core' },
  { name: 'Transformers', repo: 'huggingface/transformers', category: 'framework-tooling', tier: 'core' },
  { name: 'Accelerate', repo: 'huggingface/accelerate', category: 'framework-tooling', tier: 'extended' },
  { name: 'Optimum', repo: 'huggingface/optimum', category: 'framework-tooling', tier: 'extended' },
  { name: 'JAX', repo: 'jax-ml/jax', category: 'framework-tooling', tier: 'extended' },
  { name: 'DeepSpeed', repo: 'deepspeedai/DeepSpeed', category: 'framework-tooling', tier: 'core' },
  { name: 'Megatron-LM', repo: 'NVIDIA/Megatron-LM', category: 'framework-tooling', tier: 'extended' },
  { name: 'TorchTitan', repo: 'pytorch/torchtitan', category: 'framework-tooling', tier: 'extended' },
  { name: 'ColossalAI', repo: 'hpcaitech/ColossalAI', category: 'framework-tooling', tier: 'extended' },
  { name: 'bitsandbytes', repo: 'bitsandbytes-foundation/bitsandbytes', category: 'framework-tooling', tier: 'extended' },
  { name: 'PPL.NN', repo: 'OpenPPL/ppl.nn', category: 'framework-tooling', tier: 'extended' },
];

function slugify(name) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

function extractLogoCandidates(markdown) {
  const candidates = [];
  const expression = /(?:src=["']([^"']+)["']|!\[[^\]]*\]\(([^\s)]+))/gi;
  for (const match of markdown.matchAll(expression)) {
    const url = match[1] ?? match[2];
    if (!/logo|brand/i.test(url)) continue;
    if (/shields\.io|badge|logoColor|partners?\/|hardwares?\//i.test(url)) continue;
    candidates.push(url);
  }
  return candidates;
}

function resolveAssetUrl(repo, url) {
  if (/^https?:\/\//.test(url)) {
    const blob = url.match(/^https:\/\/github\.com\/([^/]+\/[^/]+)\/blob\/([^/]+)\/(.+?)(?:\?raw=true)?$/);
    if (blob) return `https://raw.githubusercontent.com/${blob[1]}/${blob[2]}/${blob[3]}`;
    return url;
  }
  return `https://raw.githubusercontent.com/${repo}/HEAD/${url.replace(/^\.\//, '')}`;
}

async function fetchBuffer(url) {
  const response = await fetch(url, {
    headers: { 'User-Agent': 'ai-infra-bench-logo-collector' },
    redirect: 'follow',
  });
  if (!response.ok) throw new Error(`${response.status} ${url}`);
  return Buffer.from(await response.arrayBuffer());
}

async function normalizeLogo(buffer, outputFile, cardOutputFile, trim) {
  let image = sharp(buffer, { density: 300, failOn: 'none' });
  if (trim) {
    image = image.trim({
      background: { r: 0, g: 0, b: 0, alpha: 0 },
      threshold: 12,
    });
  }
  await Promise.all([
    image
      .clone()
      .resize(256, 256, {
        fit: 'contain',
        background: { r: 0, g: 0, b: 0, alpha: 0 },
        withoutEnlargement: false,
      })
      .webp({ quality: 92, alphaQuality: 100, effort: 6 })
      .toFile(outputFile),
    image
      .clone()
      .resize(144, 40, {
        fit: 'inside',
        withoutEnlargement: false,
      })
      .webp({ quality: 92, alphaQuality: 100, effort: 6 })
      .toFile(cardOutputFile),
  ]);
}

async function collect(repository) {
  const slug = slugify(repository.name);
  const readmeUrl = `https://raw.githubusercontent.com/${repository.repo}/HEAD/README.md`;
  let logoSource = `https://github.com/${repository.repo.split('/')[0]}.png?size=512`;
  let logoSourceType = 'github_owner_avatar';
  let buffer;

  try {
    const readmeResponse = await fetch(readmeUrl, {
      headers: { 'User-Agent': 'ai-infra-bench-logo-collector' },
    });
    if (readmeResponse.ok) {
      const candidates = extractLogoCandidates(await readmeResponse.text());
      for (const candidate of candidates) {
        if (!repository.repo.startsWith('huggingface/') && /huggingface.*brand-assets/i.test(candidate)) {
          continue;
        }
        try {
          const candidateUrl = resolveAssetUrl(repository.repo, candidate);
          const candidateBuffer = await fetchBuffer(candidateUrl);
          await sharp(candidateBuffer, { density: 300, failOn: 'none' }).metadata();
          logoSource = candidateUrl;
          logoSourceType = 'repository_asset';
          buffer = candidateBuffer;
          break;
        } catch {
          continue;
        }
      }
    }
  } catch {
    // The owner avatar fallback below remains authoritative.
  }

  if (!buffer) buffer = await fetchBuffer(logoSource);
  const logoFile = `${slug}.webp`;
  await normalizeLogo(
    buffer,
    path.join(outputDir, logoFile),
    path.join(cardOutputDir, logoFile),
    logoSourceType === 'repository_asset',
  );

  return {
    ...repository,
    status: repository.status ?? 'active',
    repo_url: `https://github.com/${repository.repo}`,
    logo_file: `/logos/ai-infra/${logoFile}`,
    card_logo_file: `/logos/ai-infra/card/${logoFile}`,
    logo_source: logoSource,
    logo_source_type: logoSourceType,
  };
}

async function mapWithConcurrency(items, limit, mapper) {
  const results = new Array(items.length);
  let cursor = 0;
  async function worker() {
    while (cursor < items.length) {
      const index = cursor;
      cursor += 1;
      results[index] = await mapper(items[index]);
    }
  }
  await Promise.all(Array.from({ length: limit }, worker));
  return results;
}

await rm(outputDir, { recursive: true, force: true });
await mkdir(outputDir, { recursive: true });
await mkdir(cardOutputDir, { recursive: true });
const manifest = await mapWithConcurrency(repositories, 6, collect);
await writeFile(path.join(outputDir, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`);
await writeFile(appManifestFile, `${JSON.stringify(manifest, null, 2)}\n`);

const rows = manifest.map((item) => (
  `| ${item.name} | [${item.repo}](${item.repo_url}) | ${item.category} | ${item.tier} | ${item.status} | ${item.logo_source_type} |`
));
await writeFile(
  path.join(outputDir, 'SOURCES.md'),
  `# AI infrastructure repository logos\n\n| Project | Repository | Category | Tier | Status | Logo source |\n|---|---|---|---|---|---|\n${rows.join('\n')}\n`,
);

console.log(`Collected ${manifest.length} repository logos in ${outputDir}`);
