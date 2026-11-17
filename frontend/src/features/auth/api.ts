import { useMutation, useQuery } from "@tanstack/react-query";

import { requestTokens } from "@/network/auth";
import { api } from "@/network/client";
import { queryClient } from "@/network/query-client";
import { useAuth } from "@/stores/auth";

import type { Me } from "./types";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => api<Me>("/api/auth/me/") });
}

export function useSignIn() {
  return useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      requestTokens(email.trim(), password),
    // Nothing cached under a previous session carries over.
    onSuccess: () => queryClient.clear(),
  });
}

/** Forget the session and everything cached under it. */
export function signOut() {
  useAuth.getState().clear();
  queryClient.clear();
}
