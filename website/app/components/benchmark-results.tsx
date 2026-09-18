import leaderboard from "@/app/generated/leaderboard.json";
import { LeaderboardExplorer } from "@/app/components/leaderboard-explorer";

// The published snapshot is global. No URL or saved preference narrows it.
export function BenchmarkResults({
  headingLevel = "h2",
}: {
  headingLevel?: "h2" | "h3";
}) {
  return <LeaderboardExplorer data={leaderboard} headingLevel={headingLevel} />;
}
