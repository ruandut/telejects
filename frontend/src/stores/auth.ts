import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Tokens = { access: string; refresh: string };

type AuthState = {
  access: string | null;
  refresh: string | null;
  setTokens: (tokens: Partial<Tokens>) => void;
  clear: () => void;
};

// Tokens only. Who the user is comes from /api/auth/me/ through TanStack Query.
export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      access: null,
      refresh: null,
      setTokens: (tokens) =>
        set((s) => ({ access: tokens.access ?? s.access, refresh: tokens.refresh ?? s.refresh })),
      clear: () => set({ access: null, refresh: null }),
    }),
    { name: "telejects.auth" },
  ),
);

export const isLoggedIn = () => useAuth.getState().refresh !== null;
