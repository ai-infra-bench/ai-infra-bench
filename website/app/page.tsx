import Image from 'next/image';
import { SiteHeader } from '@/app/components/site-header';
import { TaskExplorer } from '@/app/components/task-explorer';
import { withBasePath } from '@/app/lib/base-path';
import { getRepositoryBrand } from '@/app/lib/repository-brand';
import { absoluteSiteUrl } from '@/app/lib/site-url';
import { formatTaskTitle } from '@/app/lib/task-format';
import { tasks } from '@/app/lib/tasks';

export default function Home() {
  const description =
    'AI Infra Bench evaluates frontier coding agents on expert-reviewed, real-world AI infrastructure engineering tasks, beginning with vLLM.';
  const taskSummaries = tasks.map((task) => {
    const repositoryBrand = getRepositoryBrand(task.repository);
    return {
      slug: task.slug,
      description: task.description,
      workloadType: task.workloadType,
      subsystems: task.subsystems,
      repository: task.repository,
      repositoryName: repositoryBrand?.name ?? null,
      repositoryLogo: repositoryBrand?.card_logo_file ?? null,
      repositoryLogoKind: repositoryBrand?.card_logo_kind ?? null,
      accelerator: task.accelerator,
    };
  });
  const structuredData = {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'WebSite',
        '@id': `${absoluteSiteUrl('/')}#website`,
        name: 'AI Infra Bench',
        alternateName: 'AI Infrastructure Benchmark',
        url: absoluteSiteUrl('/'),
        description,
        inLanguage: 'en',
        sameAs: ['https://github.com/ai-infra-bench/ai-infra-bench'],
      },
      {
        '@type': 'Dataset',
        '@id': `${absoluteSiteUrl('/')}#dataset`,
        name: 'AI Infra Bench task registry',
        description,
        url: absoluteSiteUrl('/'),
        license: 'https://www.apache.org/licenses/LICENSE-2.0',
        isAccessibleForFree: true,
        keywords: [
          'AI infrastructure',
          'coding agents',
          'large language models',
          'software engineering benchmark',
          'vLLM',
        ],
        creator: {
          '@type': 'Organization',
          name: 'AI Infra Bench',
          url: absoluteSiteUrl('/'),
        },
        hasPart: tasks.map((task) => ({
          '@type': 'CreativeWork',
          name: formatTaskTitle(task.slug),
          description: task.description,
          url: absoluteSiteUrl(`/tasks/${task.slug}`),
        })),
      },
    ],
  };

  return (
    <main>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(structuredData).replaceAll('<', '\\u003c'),
        }}
      />
      <SiteHeader />

      <section className="hero" aria-labelledby="site-title">
        <h1 className="wordmark-frame" id="site-title">
          <Image
            className="wordmark"
            src={withBasePath('/brand/ai-infra-bench-wordmark.webp')}
            alt="AI Infra Bench"
            width={2059}
            height={764}
            priority
          />
          <span className="sr-only">AI Infra Bench</span>
        </h1>
        <p>An open benchmark for frontier coding agents on real-world AI infrastructure engineering tasks.</p>
        <a href="#tasks">Browse tasks</a>
      </section>

      <TaskExplorer tasks={taskSummaries} />

      <footer className="site-footer">
        <span>AI Infra Bench</span>
        <span>Apache-2.0</span>
      </footer>
    </main>
  );
}
