import type { ReactNode } from "react";
import { SiteHeader } from "@/app/components/site-header";
import { SiteFooter } from "@/app/components/site-footer";

export function SiteShell({
  children,
  current,
}: {
  children: ReactNode;
  current?: "home" | "leaderboard" | "tasks";
}) {
  const isHome = current === "home";
  return (
    <main className={"design-shell" + (isHome ? " is-home" : "")}>
      <SiteHeader current={current} />
      <div className="design-content">{children}</div>
      <SiteFooter />
    </main>
  );
}
