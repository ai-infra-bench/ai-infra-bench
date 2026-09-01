import Link from 'next/link';

export function SiteHeader() {
  return (
    <header className="site-header">
      <Link className="header-name" href="/">AI Infra Bench</Link>
      <nav aria-label="Primary navigation">
        <Link href="/#tasks">Tasks</Link>
        <a href="https://github.com/ai-infra-bench/ai-infra-bench">GitHub</a>
      </nav>
    </header>
  );
}
