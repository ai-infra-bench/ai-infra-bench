import { ArrowLeftIcon, ArrowRightIcon } from "@radix-ui/react-icons";
import { withRouteBasePath } from "@/app/lib/base-path";

type AdjacentTask = { slug: string; title: string };
export function SiteFooter({
  previous,
  next,
  taskNavigation = false,
}: {
  previous?: AdjacentTask | null;
  next?: AdjacentTask | null;
  taskNavigation?: boolean;
}) {
  return (
    <footer className="unified-footer">
      {taskNavigation && (
        <nav
          className="footer-pagination chrome-inner"
          aria-label="Adjacent tasks"
        >
          <div>
            {previous && (
              <a href={withRouteBasePath("/tasks/" + previous.slug)}>
                <ArrowLeftIcon aria-hidden="true" />
                <span>
                  <small>Previous task</small>
                  <span>{previous.title}</span>
                </span>
              </a>
            )}
          </div>
          <div>
            {next && (
              <a href={withRouteBasePath("/tasks/" + next.slug)}>
                <span>
                  <small>Next task</small>
                  <span>{next.title}</span>
                </span>
                <ArrowRightIcon aria-hidden="true" />
              </a>
            )}
          </div>
        </nav>
      )}
      <div className="footer-identity chrome-inner">
        <a href={withRouteBasePath("/")}>AI Infra Bench</a>
        <span>Apache-2.0</span>
      </div>
    </footer>
  );
}
