/** Shown when the server would refuse a whole page anyway. */
export function NoAccess({ section }: { section: string }) {
  return (
    <div className="mx-auto w-full max-w-xl p-4 md:p-8">
      <div className="rounded-xl border bg-card p-6 text-center">
        <h1 className="text-lg font-semibold">You don't have access to {section}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Ask one of your company's Admins if something needs to change.
        </p>
      </div>
    </div>
  );
}
