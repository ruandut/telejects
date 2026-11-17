import type { ReactNode } from "react";

import { ThemeToggle } from "@/components/theme-toggle";
import { Wordmark } from "@/components/wordmark";

import { BrandPanel } from "./brand-panel";

const YEAR = new Date().getFullYear();

/** The signed-out layout: the brand panel beside a narrow column for one form. */
export function AuthShell({
  title,
  description,
  children,
}: {
  title: string;
  description?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="grid min-h-svh lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
      <BrandPanel />

      <main className="relative flex min-h-svh flex-col px-6 py-6 sm:px-10">
        <div className="flex items-center justify-between">
          <Wordmark className="text-sm text-primary lg:invisible" />
          <ThemeToggle />
        </div>

        <div className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-sm">
            <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
            {description && <p className="mt-2 text-sm text-muted-foreground">{description}</p>}
            <div className="mt-8">{children}</div>
          </div>
        </div>

        <p className="text-center text-xs text-muted-foreground lg:text-left">© {YEAR} Telejects</p>
      </main>
    </div>
  );
}
