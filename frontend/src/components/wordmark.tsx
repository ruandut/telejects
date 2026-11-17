import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

/** Placeholder wordmark until there's a logo. Colour follows the surrounding text. */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span
      role="img"
      aria-label="Telejects"
      className={cn("inline-flex w-fit items-center gap-2 self-start", className)}
    >
      <Mark aria-hidden className="size-[1.6em]" />
      <span aria-hidden className="text-[1.15em] font-semibold tracking-tight">
        Telejects
      </span>
    </span>
  );
}

/** The square mark on its own, for the favicon and the collapsed sidebar. */
export function Mark({ className, ...props }: ComponentProps<"svg">) {
  return (
    <svg viewBox="0 0 32 32" className={className} {...props}>
      <rect width="32" height="32" rx="7" fill="currentColor" />
      <path
        d="M9 10h14M16 10v13"
        className="stroke-background"
        strokeWidth="3"
        strokeLinecap="round"
        fill="none"
      />
      <circle cx="23" cy="22" r="2.5" className="fill-brand-accent" />
    </svg>
  );
}
