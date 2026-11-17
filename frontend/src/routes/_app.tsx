import { createFileRoute, Link, Outlet, redirect } from "@tanstack/react-router";

import { AppSidebar } from "@/components/app-sidebar";
import { ThemeToggle } from "@/components/theme-toggle";
import { Separator } from "@/components/ui/separator";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { Wordmark } from "@/components/wordmark";
import { RealmGate } from "@/features/realms/realm-gate";
import { isLoggedIn } from "@/stores/auth";

// Pathless layout: every signed-in screen renders beside the sidebar (a drawer on a phone),
// inside the tab's company.
export const Route = createFileRoute("/_app")({
  beforeLoad: () => {
    if (!isLoggedIn()) throw redirect({ to: "/login" });
  },
  component: AppLayout,
});

function AppLayout() {
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="min-w-0">
        <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center gap-2 border-b bg-background/90 px-4 backdrop-blur">
          <SidebarTrigger className="-ml-1" />
          <Separator
            orientation="vertical"
            className="mr-1 data-[orientation=vertical]:h-4 data-[orientation=vertical]:self-center md:hidden"
          />
          <Link
            to="/"
            className="rounded-md text-primary md:hidden outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <Wordmark className="text-xs" />
          </Link>
          <div className="flex-1" />
          <ThemeToggle />
        </header>
        <RealmGate>
          <Outlet />
        </RealmGate>
      </SidebarInset>
    </SidebarProvider>
  );
}
