import type { CSSProperties } from 'react';
import type { Metadata } from 'next';
import { Geist, Geist_Mono, Newsreader } from 'next/font/google';
import { withBasePath } from '@/app/lib/base-path';
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
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3000'),
  title: 'AI Infra Bench | AI Infrastructure Benchmark',
  description:
    'AI Infra Bench evaluates frontier models on real-world AI infrastructure engineering workloads, beginning with vLLM.',
  icons: {
    icon: [{ url: withBasePath('/favicon.svg'), type: 'image/svg+xml' }],
  },
  openGraph: {
    title: 'AI Infra Bench | AI Infrastructure Benchmark',
    description:
      'AI Infra Bench evaluates frontier models on real-world AI infrastructure engineering workloads, beginning with vLLM.',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'AI Infra Bench | AI Infrastructure Benchmark',
    description:
      'AI Infra Bench evaluates frontier models on real-world AI infrastructure engineering workloads, beginning with vLLM.',
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
