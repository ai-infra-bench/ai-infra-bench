import Image from 'next/image';
import { SiteHeader } from '@/app/components/site-header';
import { TaskExplorer } from '@/app/components/task-explorer';
import { tasks } from '@/app/lib/tasks';

export default function Home() {
  const taskSummaries = tasks.map((task) => ({
    slug: task.slug,
    description: task.description,
    workloadType: task.workloadType,
    subsystems: task.subsystems,
    repository: task.repository,
    accelerator: task.accelerator,
  }));

  return (
    <main>
      <SiteHeader />

      <section className="hero" aria-labelledby="site-title">
        <h1 className="sr-only" id="site-title">AI Infra Bench</h1>
        <div className="wordmark-frame">
          <Image
            className="wordmark"
            src="/brand/ai-infra-bench-wordmark.png"
            alt="AI Infra Bench"
            width={2059}
            height={764}
            priority
          />
        </div>
        <p>How much real AI-inference engineering work can frontier models solve?</p>
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
