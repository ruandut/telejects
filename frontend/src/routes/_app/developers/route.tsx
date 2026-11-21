import { createFileRoute, Link, Outlet } from "@tanstack/react-router";
import { BookOpen, ExternalLink, KeyRound } from "lucide-react";

import { API_DOCS_URL } from "@/features/api-clients/docs";

export const Route = createFileRoute("/_app/developers")({
  component: DevelopersLayout,
});

const tab =
  "-mb-px inline-flex shrink-0 items-center gap-1.5 border-b-2 border-transparent px-1 pb-2.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground data-[status=active]:border-primary data-[status=active]:text-foreground [&_svg]:size-4";

function DevelopersLayout() {
  return (
    <div className="mx-auto w-full max-w-5xl p-4 md:p-8">
      <h1 className="text-2xl font-semibold tracking-tight">Developers</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Connect your own systems to Telejects' feasibilities and quotes.
      </p>
      <nav className="mt-5 flex flex-wrap gap-x-5 border-b" aria-label="Developers">
        <Link to="/developers/credentials" className={tab}>
          <KeyRound /> Server credentials
        </Link>
        <a href={API_DOCS_URL} target="_blank" rel="noreferrer" className={tab}>
          <BookOpen /> API <span className="hidden sm:inline">documentation</span>
          <span className="sm:hidden">docs</span>
          <ExternalLink className="size-3.5! opacity-60" aria-label="(opens in a new tab)" />
        </a>
      </nav>
      <Outlet />
    </div>
  );
}
