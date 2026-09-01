import { withRouteBasePath } from '@/app/lib/base-path';

export function SiteHeader() {
  return (
    <header className="site-header">
      <a className="header-name" href={withRouteBasePath('/')} aria-label="AI Infra Bench">
        <span className="header-wordmark" aria-hidden="true">
          <span>AI</span><span className="header-infra-i" /><span>nfra Bench</span>
        </span>
      </a>
      <nav aria-label="Primary navigation">
        <a href={withRouteBasePath('/#tasks')}>Tasks</a>
        <a href="https://github.com/ai-infra-bench/ai-infra-bench">GitHub</a>
      </nav>
    </header>
  );
}
