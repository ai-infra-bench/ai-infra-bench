import { LeaderboardExplorer } from '@/app/components/leaderboard-explorer';
import leaderboard from '@/app/generated/leaderboard.json';

export function HomeLeaderboard() {
  return (
    <section className="home-section home-leaderboard" id="leaderboard" aria-labelledby="leaderboard-title">
      <header className="leaderboard-heading">
        <h2 className="home-section-title" id="leaderboard-title">Leaderboard</h2>
        <p>
          <span>{leaderboard.release.taskCount} tasks</span>
          <span>{leaderboard.release.expectedAttempts} runs per task</span>
          <span>{leaderboard.release.label}</span>
        </p>
      </header>

      <LeaderboardExplorer data={leaderboard} />
    </section>
  );
}
