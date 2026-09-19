import type { Metadata } from "next";
import { ChartHome } from "@/app/components/chart-home";
export const metadata: Metadata = { alternates: { canonical: "/" } };
export default function Home() {
  return <ChartHome />;
}
