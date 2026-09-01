import repositoryLogos from '@/app/generated/repository-logos.json';

type RepositoryLogo = {
  name: string;
  repo: string;
  card_logo_file: string;
};

const repositoryLogoMap = new Map(
  (repositoryLogos as RepositoryLogo[]).map((item) => [item.repo.toLowerCase(), item]),
);

export function getRepositoryBrand(repository: string | null) {
  if (!repository) return null;
  return repositoryLogoMap.get(repository.toLowerCase()) ?? null;
}
