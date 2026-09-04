import type { CSSProperties } from 'react';
import type { Metadata } from 'next';
import { Geist, Geist_Mono, Newsreader } from 'next/font/google';
import { withBasePath } from '@/app/lib/base-path';
import { siteUrl } from '@/app/lib/site-url';
import './globals.css';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

const newsreader = Newsreader({
  variable: '--font-newsreader',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  metadataBase: siteUrl,
  title: {
    default: 'AI Infra Bench: Real-World AI Infrastructure Benchmark',
    template: '%s | AI Infra Bench',
  },
  description:
    'AI Infra Bench evaluates frontier coding agents on expert-reviewed, real-world AI infrastructure engineering tasks, beginning with vLLM.',
  keywords: [
    'AI infrastructure benchmark',
    'coding agent benchmark',
    'LLM benchmark',
    'vLLM benchmark',
    'software engineering benchmark',
  ],
  alternates: {
    canonical: '/',
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      'max-image-preview': 'large',
      'max-snippet': -1,
      'max-video-preview': -1,
    },
  },
  icons: {
    icon: [{ url: withBasePath('/favicon.svg'), type: 'image/svg+xml' }],
  },
  openGraph: {
    title: 'AI Infra Bench: Real-World AI Infrastructure Benchmark',
    description:
      'Evaluate frontier coding agents on expert-reviewed, real-world AI infrastructure engineering tasks, beginning with vLLM.',
    type: 'website',
    url: '/',
    siteName: 'AI Infra Bench',
    locale: 'en_US',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'AI Infra Bench: Real-World AI Infrastructure Benchmark',
    description:
      'Evaluate frontier coding agents on expert-reviewed, real-world AI infrastructure engineering tasks, beginning with vLLM.',
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const bodyStyle = {
    '--paper-texture-url': `url("${withBasePath('/brand/paper-texture.webp')}")`,
  } as CSSProperties;

  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} ${newsreader.variable} antialiased`}
        style={bodyStyle}
      >
        {children}
      </body>
    </html>
  );
}
