import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";

import { api } from "@/network/client";
import { useAuth, type Tokens } from "@/stores/auth";

export type PasswordChange = { current_password: string; new_password: string };

/**
 * Change my own password (0002). Every other browser is signed out; this one gets fresh tokens
 * in the answer and keeps going.
 */
export function useChangePassword() {
  return useMutation({
    mutationFn: (change: PasswordChange) =>
      api<Tokens>("/api/auth/password/", { method: "POST", body: JSON.stringify(change) }),
    onSuccess: (tokens) => {
      useAuth.getState().setTokens(tokens);
      toast.success("Password changed");
    },
  });
}
