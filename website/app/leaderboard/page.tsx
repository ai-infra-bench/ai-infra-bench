import type { Metadata } from "next";
import { LeaderboardPage } from "@/app/components/leaderboard-page";
import { SiteShell } from "@/app/components/site-shell";
export const metadata: Metadata = {
  title: "Leaderboard | AI Infra Bench",
  alternates: { canonical: "/leaderboard" },
};
export default function Leaderboard() {
  return (
    <SiteShell current="leaderboard">
      <LeaderboardPage />
    </SiteShell>
  );
}
