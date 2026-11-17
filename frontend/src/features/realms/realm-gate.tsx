import { Fragment, useEffect, type ReactNode } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/features/auth/api";
import { queryClient } from "@/network/query-client";
import { liveSocket } from "@/network/socket";
import { useRealm } from "@/stores/realm";

/**
 * Point this tab at another company. Everything cached belongs to the old one, so it's reset.
 * /me is keyed by company, so it needs no reset.
 */
export function enterRealm(realmId: number | null) {
  useRealm.getState().setRealmId(realmId);
  void queryClient.resetQueries({ predicate: (query) => query.queryKey[0] !== "me" });
}

/**
 * Settles which company this tab works in before any company data loads. The page is keyed by
 * the company, so switching remounts it and nothing from the old one can linger on screen.
 */
export function RealmGate({ children }: { children: ReactNode }) {
  const me = useMe();
  const realmId = useRealm((s) => s.realmId);
  const current = me.data?.realm?.id ?? null;

  useEffect(() => {
    if (!me.data) return;
    // No company chosen in this tab yet: take the server's. Or the chosen one is gone: forget
    // it, which refetches /me without the header.
    if (realmId === null ? current !== null : current !== realmId) enterRealm(current);
  }, [me.data, current, realmId]);

  const settled = realmId !== null && current === realmId;
  // The live socket works in the settled company only, and follows it when it changes.
  useEffect(() => liveSocket.setRealm(settled ? realmId : null), [settled, realmId]);

  if (me.data && !me.data.realm && !me.data.realms.length) return <NoRealm />;
  if (!settled) {
    return (
      <div className="mx-auto grid w-full max-w-5xl gap-3 p-4 md:p-8">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }
  return <Fragment key={realmId}>{children}</Fragment>;
}

function NoRealm() {
  return (
    <div className="mx-auto w-full max-w-xl p-4 md:p-8">
      <div className="rounded-xl border bg-card p-6 text-center">
        <h2 className="text-lg font-semibold">You're not part of any company yet</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Ask your company's administrator to add you.
        </p>
      </div>
    </div>
  );
}
