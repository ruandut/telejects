import { useAuth, type Tokens } from "@/stores/auth";

import { ApiError } from "./errors";

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

/** Exchange an email and password for a token pair, and keep it. */
export async function requestTokens(email: string, password: string): Promise<void> {
  const res = await fetch("/api/auth/token/", json({ email, password }));
  if (!res.ok) {
    if (res.status === 401) throw new Error("That email and password don't match.");
    if (res.status === 429) throw new Error("Too many attempts. Wait a minute and try again.");
    throw new ApiError(res.status, await res.json().catch(() => null));
  }
  useAuth.getState().setTokens((await res.json()) as Tokens);
}

// Concurrent 401s share one refresh request instead of racing (refresh tokens rotate).
let refreshing: Promise<string | null> | null = null;

export function refreshAccessToken(): Promise<string | null> {
  refreshing ??= (async () => {
    const { refresh, setTokens, clear } = useAuth.getState();
    if (!refresh) return null;
    const res = await fetch("/api/auth/token/refresh/", json({ refresh }));
    if (!res.ok) {
      clear();
      return null;
    }
    const tokens = (await res.json()) as Partial<Tokens>;
    setTokens(tokens);
    return tokens.access ?? null;
  })().finally(() => {
    refreshing = null;
  });
  return refreshing;
}
