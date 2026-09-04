const DEFAULT_SITE_URL = 'https://ai-infra-bench.github.io';

export const siteUrl = new URL(
  process.env.NEXT_PUBLIC_SITE_URL ?? DEFAULT_SITE_URL,
);

export function absoluteSiteUrl(path = '/') {
  return new URL(path, siteUrl).toString();
}
