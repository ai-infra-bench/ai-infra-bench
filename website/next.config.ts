import type { NextConfig } from 'next';

const isGitHubPages = process.env.GITHUB_PAGES === 'true';
const repositoryName = process.env.GITHUB_REPOSITORY?.split('/').at(-1) ?? 'ai-infra-bench';
const pagesBasePath = process.env.GITHUB_PAGES_BASE_PATH ?? `/${repositoryName}`;

const nextConfig: NextConfig = isGitHubPages
  ? {
      output: 'export',
      trailingSlash: false,
      assetPrefix: pagesBasePath,
      images: { unoptimized: true },
      env: { NEXT_PUBLIC_BASE_PATH: pagesBasePath },
    }
  : {
      env: { NEXT_PUBLIC_BASE_PATH: '' },
    };

export default nextConfig;
