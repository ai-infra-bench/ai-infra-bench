import { BenchmarkResults } from "@/app/components/benchmark-results";
import leaderboard from "@/app/generated/leaderboard.json";
import { PrintComparison } from "@/app/components/print-comparison";

export function LeaderboardPage() {
  return (
    <section
      className="design-results"
      id="leaderboard"
      aria-labelledby="leaderboard-title"
    >
      <header className="results-heading">
        <h1 id="leaderboard-title">Leaderboard</h1>
        <p>
          {leaderboard.release.taskCount} tasks <span>/</span>{" "}
          {leaderboard.release.expectedAttempts} runs per task <span>/</span>{" "}
          {leaderboard.release.label}
        </p>
      </header>
      <PrintComparison />
      <BenchmarkResults />
    </section>
  );
}
