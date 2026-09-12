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
import "./editorial-index.css";

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

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
const siteName = "AI Infra Bench";
const siteDescription =
  "AI Infra Bench evaluates frontier models on real-world AI infrastructure engineering workloads, beginning with vLLM.";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: "AI Infra Bench | AI Infrastructure Benchmark",
  description: siteDescription,
  icons: {
    icon: [
      {
        url: withBasePath("/favicon-32.png"),
        type: "image/png",
        sizes: "32x32",
      },
      {
        url: withBasePath("/favicon.svg?v=contour-mono"),
        type: "image/svg+xml",
        sizes: "any",
      },
    ],
  },
  openGraph: {
    title: "AI Infra Bench | AI Infrastructure Benchmark",
    description: siteDescription,
    siteName,
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "AI Infra Bench | AI Infrastructure Benchmark",
    description: siteDescription,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="editorial-index">
      <body
        className={`${geistSans.variable} ${geistMono.variable} ${displayFont.variable} antialiased craft-press`}
      >
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "WebSite",
              name: siteName,
              alternateName: "AI infrastructure benchmark",
              description: siteDescription,
              url: new URL("/", siteUrl).toString(),
              sameAs: ["https://github.com/ai-infra-bench/ai-infra-bench"],
            }),
          }}
        />
        {children}
      </body>
    </html>
  );
}
