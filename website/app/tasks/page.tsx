import type { Metadata } from "next";
import { CatalogueBrowser } from "@/app/components/catalogue-browser";
import { SiteShell } from "@/app/components/site-shell";
import { tasks } from "@/app/lib/tasks";
export const metadata: Metadata = {
  title: "Tasks | AI Infra Bench",
  alternates: { canonical: "/tasks" },
};
export default function TaskCatalogue() {
  return (
    <SiteShell current="tasks">
      <CatalogueBrowser tasks={tasks} pageSize={8} />
    </SiteShell>
  );
}
