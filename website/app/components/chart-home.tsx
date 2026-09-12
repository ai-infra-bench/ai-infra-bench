import { SiteShell } from "@/app/components/site-shell";
import { PrintComparison } from "@/app/components/print-comparison";
import { tasks } from "@/app/lib/tasks";
import { BenchmarkResults } from "@/app/components/benchmark-results";
import { HomeTasks } from "@/app/components/home-tasks";
import { MastheadVignette } from "@/app/components/masthead-vignette";
export function ChartHome() {
  return (
    <SiteShell current="home">
      <section
        className="print-cover print-layout-top"
        aria-labelledby="print-title"
      >
        <header className="print-masthead">
          <h1 id="print-title">AI Infra Bench</h1>
          <p>
            How much real AI infrastructure engineering work can frontier models
            solve?
          </p>
          <MastheadVignette />
        </header>
        <PrintComparison />
      </section>
      <div className="home-followup">
        <div className="home-results" id="leaderboard">
          <BenchmarkResults />
        </div>
        <HomeTasks tasks={tasks} />
      </div>
    </SiteShell>
  );
}
