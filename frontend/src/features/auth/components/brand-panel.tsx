import { Wordmark } from "@/components/wordmark";

/** The deep half of the sign-in screen. The same in both themes, like the brand itself. */
export function BrandPanel() {
  return (
    <aside className="relative hidden overflow-hidden bg-brand-deeper text-brand-on-deep lg:flex lg:flex-col lg:justify-between lg:p-12 xl:p-16">
      <div
        aria-hidden
        className="absolute inset-0 bg-[radial-gradient(120%_90%_at_0%_0%,var(--brand-deep)_0%,transparent_62%)]"
      />
      <Wordmark className="relative text-xl" />
      <h2 className="relative max-w-md text-4xl leading-[1.15] font-light tracking-tight text-balance">
        Telejects
      </h2>
    </aside>
  );
}
