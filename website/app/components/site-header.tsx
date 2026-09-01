import Link from 'next/link';

export function SiteHeader() {
  return (
    <header className="site-header">
      <Link className="header-name" href="/" aria-label="AI Infra Bench">
        <span className="header-wordmark" aria-hidden="true">
          <span>AI </span><span className="header-infra-i">I</span><span>nfra Bench</span>
        </span>
      </Link>
      <nav aria-label="Primary navigation">
        <Link href="/#tasks">Tasks</Link>
        <a href="https://github.com/ai-infra-bench/ai-infra-bench">GitHub</a>
      </nav>
    </header>
  );
}
