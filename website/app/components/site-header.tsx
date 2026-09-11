import { withRouteBasePath } from "@/app/lib/base-path";
export function SiteHeader({
  current,
}: {
  current?: "home" | "leaderboard" | "tasks";
}) {
  return (
    <header className="site-header">
      <div className="chrome-inner">
        <a
          className="header-name"
          href={withRouteBasePath("/")}
          aria-current={current === "home" ? "page" : undefined}
        >
          AI Infra Bench
        </a>
        <nav aria-label="Primary navigation">
          <a
            href={withRouteBasePath("/leaderboard")}
            aria-current={current === "leaderboard" ? "page" : undefined}
          >
            Leaderboard
          </a>
          <a
            href={withRouteBasePath("/tasks")}
            aria-current={current === "tasks" ? "page" : undefined}
          >
            Tasks
          </a>
          <a
            className="github-link"
            href="https://github.com/ai-infra-bench/ai-infra-bench"
          >
            GitHub
          </a>
        </nav>
      </div>
    </header>
  );
}
