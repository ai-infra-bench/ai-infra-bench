import type { CSSProperties } from 'react';
import Image from 'next/image';
import repositoryLogos from '@/app/generated/repository-logos.json';

type LogoRecord = {
  name: string;
  repo: string;
  card_logo_file: string;
  card_logo_kind: 'mark' | 'wordmark';
};

type BurstNode = {
  repo: string;
  x: number;
  y: number;
  mobileX?: number;
  mobileY?: number;
  size: 'large' | 'medium' | 'small';
  opacity: number;
};

type BurstStyle = CSSProperties & Record<`--${string}`, string | number>;

const logoMap = new Map(
  (repositoryLogos as LogoRecord[]).map((logo) => [logo.repo.toLowerCase(), logo]),
);

const nodes: BurstNode[] = [
  { repo: 'vllm-project/vllm', x: 8, y: 10, mobileX: 12, mobileY: 10, size: 'large', opacity: 0.9 },
  { repo: 'sgl-project/sglang', x: 27, y: 16, mobileX: 38, mobileY: 7, size: 'large', opacity: 0.84 },
  { repo: 'pytorch/pytorch', x: 46, y: 8, mobileX: 66, mobileY: 9, size: 'large', opacity: 0.88 },
  { repo: 'triton-lang/triton', x: 65, y: 16, mobileX: 89, mobileY: 11, size: 'large', opacity: 0.84 },
  { repo: 'huggingface/transformers', x: 83, y: 9, mobileX: 9, mobileY: 31, size: 'large', opacity: 0.86 },
  { repo: 'NVIDIA/TensorRT-LLM', x: 96, y: 20, mobileX: 91, mobileY: 31, size: 'large', opacity: 0.8 },
  { repo: 'ray-project/ray', x: 6, y: 31, mobileX: 10, mobileY: 57, size: 'medium', opacity: 0.8 },
  { repo: 'flashinfer-ai/flashinfer', x: 17, y: 40, mobileX: 90, mobileY: 57, size: 'medium', opacity: 0.82 },
  { repo: 'kvcache-ai/Mooncake', x: 4, y: 52, size: 'medium', opacity: 0.78 },
  { repo: 'InternLM/lmdeploy', x: 15, y: 62, size: 'medium', opacity: 0.76 },
  { repo: 'deepspeedai/DeepSpeed', x: 6, y: 71, size: 'medium', opacity: 0.74 },
  { repo: 'tile-ai/tilelang', x: 94, y: 31, size: 'small', opacity: 0.76 },
  { repo: 'Dao-AILab/flash-attention', x: 83, y: 40, size: 'medium', opacity: 0.8 },
  { repo: 'llm-d/llm-d', x: 96, y: 52, size: 'small', opacity: 0.74 },
  { repo: 'NVIDIA/cutlass', x: 85, y: 62, size: 'small', opacity: 0.72 },
  { repo: 'jax-ml/jax', x: 94, y: 71, size: 'medium', opacity: 0.76 },
  { repo: 'ggml-org/llama.cpp', x: 5, y: 84, size: 'small', opacity: 0.7 },
  { repo: 'LMCache/LMCache', x: 19, y: 79, size: 'small', opacity: 0.76 },
  { repo: 'facebookresearch/xformers', x: 33, y: 91, size: 'small', opacity: 0.72 },
  { repo: 'NVIDIA/nccl', x: 48, y: 84, size: 'small', opacity: 0.7 },
  { repo: 'ovg-project/kvcached', x: 64, y: 92, size: 'small', opacity: 0.72 },
  { repo: 'NVIDIA/Megatron-LM', x: 79, y: 80, size: 'small', opacity: 0.72 },
  { repo: 'pytorch/torchtitan', x: 95, y: 84, size: 'small', opacity: 0.7 },
  { repo: 'hpcaitech/ColossalAI', x: 50, y: 96, size: 'small', opacity: 0.68 },
];

export function HeroLogoBurst() {
  return (
    <div className="hero-logo-burst" aria-hidden="true">
      {nodes.map((node, index) => {
        const logo = logoMap.get(node.repo.toLowerCase());
        if (!logo) return null;

        const mobileX = node.mobileX ?? node.x;
        const mobileY = node.mobileY ?? node.y;
        const style: BurstStyle = {
          '--node-x': `${node.x}%`,
          '--node-y': `${node.y}%`,
          '--node-mobile-x': `${mobileX}%`,
          '--node-mobile-y': `${mobileY}%`,
          '--node-burst-x': `${28 - node.x}vw`,
          '--node-burst-y': `${48 - node.y}vh`,
          '--node-mobile-burst-x': `${50 - mobileX}vw`,
          '--node-mobile-burst-y': `${40 - mobileY}vh`,
          '--node-delay': `${80 + index * 24}ms`,
          '--node-opacity': node.opacity,
        };

        return (
          <span
            className={`hero-logo-node is-${node.size}`}
            style={style}
            key={node.repo}
          >
            <Image
              className={`hero-logo-image is-${logo.card_logo_kind}`}
              src={logo.card_logo_file}
              alt=""
              width={144}
              height={40}
              unoptimized
            />
          </span>
        );
      })}
    </div>
  );
}
