import type { Metadata } from "next";
import { DM_Sans, Geist_Mono, EB_Garamond } from "next/font/google";
import { withBasePath } from "@/app/lib/base-path";
import "./globals.css";
import "./site.css";
import "./site-chrome.css";
import "./print-home.css";
import "./catalogue.css";
import "./section-surfaces.css";
import "./page-flow.css";
import "./results-layout.css";
import "./catalogue-browser.css";
import "./masthead-vignette.css";
import "./plot-interactions.css";
import "./site-interactions.css";

const geistSans = DM_Sans({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const displayFont = EB_Garamond({
  variable: "--font-print-display",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000",
  ),
  title: "AI Infra Bench | AI Infrastructure Benchmark",
  description:
    "AI Infra Bench evaluates frontier models on real-world AI infrastructure engineering workloads, beginning with vLLM.",
  icons: {
    icon: [{ url: withBasePath("/favicon.svg"), type: "image/svg+xml" }],
  },
  openGraph: {
    title: "AI Infra Bench | AI Infrastructure Benchmark",
    description:
      "AI Infra Bench evaluates frontier models on real-world AI infrastructure engineering workloads, beginning with vLLM.",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "AI Infra Bench | AI Infrastructure Benchmark",
    description:
      "AI Infra Bench evaluates frontier models on real-world AI infrastructure engineering workloads, beginning with vLLM.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} ${displayFont.variable} antialiased craft-press`}
      >
        {children}
      </body>
    </html>
  );
}
