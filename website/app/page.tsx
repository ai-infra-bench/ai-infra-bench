import type { Metadata } from 'next';
import Image from 'next/image';
import { SiteHeader } from '@/app/components/site-header';
import { TaskExplorer } from '@/app/components/task-explorer';
import { withBasePath } from '@/app/lib/base-path';
import { getRepositoryBrand } from '@/app/lib/repository-brand';
import { tasks } from '@/app/lib/tasks';

export const metadata: Metadata = {
  alternates: { canonical: '/' },
};

export default function Home() {
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
  return (
    <main>
      <SiteHeader />

      <section className="hero" aria-labelledby="site-title">
        <h1 className="sr-only" id="site-title">AI Infra Bench</h1>
        <div className="wordmark-frame">
          <Image
            className="wordmark"
            src={withBasePath('/brand/ai-infra-bench-wordmark.webp')}
            alt="AI Infra Bench"
            width={2059}
            height={764}
            priority
          />
        </div>
        <p>How much real AI infrastructure engineering work can frontier models solve?</p>
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
