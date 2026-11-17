import { useMutation, useQuery } from "@tanstack/react-query";

import { requestTokens } from "@/network/auth";
import { api } from "@/network/client";
import { queryClient } from "@/network/query-client";
import { useAuth } from "@/stores/auth";
import { useRealm } from "@/stores/realm";

import type { Me } from "./types";

/** Keyed by the tab's company, as the answer depends on the X-Realm header sent with it. */
export function useMe() {
  const realmId = useRealm((s) => s.realmId);
  return useQuery({ queryKey: ["me", realmId], queryFn: () => api<Me>("/api/auth/me/") });
}

export function useSignIn() {
  return useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      requestTokens(email.trim(), password),
    onSuccess: () => {
      // Start from this account's own company, not whatever this browser last showed.
      useRealm.getState().setRealmId(null);
      queryClient.clear();
    },
  });
}

/** Forget the session and everything cached under it. */
export function signOut() {
  useAuth.getState().clear();
  useRealm.getState().setRealmId(null);
  queryClient.clear();
}
