/**
 * The network layer: the only place in the app that calls fetch. Features build their query and
 * mutation hooks on `api()`.
 */
import { useAuth } from "@/stores/auth";
import { useRealm } from "@/stores/realm";

import { refreshAccessToken } from "./auth";
import { ApiError } from "./errors";
import { queryClient } from "./query-client";

async function authedFetch(path: string, init: RequestInit): Promise<Response> {
  const send = (token: string | null) => {
    const headers = new Headers(init.headers);
    // The browser sets a FormData body's Content-Type itself, including the boundary.
    if (!headers.has("Content-Type") && !(init.body instanceof FormData))
      headers.set("Content-Type", "application/json");
    if (token) headers.set("Authorization", `Bearer ${token}`);
    // Every request names the company this tab works in; the server refuses ones we aren't in.
    const { realmId } = useRealm.getState();
    if (realmId !== null && !headers.has("X-Realm")) headers.set("X-Realm", String(realmId));
    return fetch(path, { ...init, headers });
  };

  let res = await send(useAuth.getState().access);
  if (res.status === 401) {
    const fresh = await refreshAccessToken();
    if (fresh) res = await send(fresh);
  }
  if (res.status === 401) {
    useAuth.getState().clear();
    window.location.assign("/login");
  }
  if (res.status === 403) {
    // Removed from this company, or it's gone: /me works out where to go instead.
    const body = (await res
      .clone()
      .json()
      .catch(() => null)) as { code?: string } | null;
    if (body?.code === "not_member" || body?.code === "no_realm")
      void queryClient.invalidateQueries({ queryKey: ["me"] });
  }
  return res;
}

/** fetch() for /api/* with the JWT and company attached and one transparent refresh on 401. */
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await authedFetch(path, init);
  const body: unknown = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, body);
  return body as T;
}

/** A file from /api/* (an export), for saving. */
export async function apiFile(path: string): Promise<{ blob: Blob; filename: string }> {
  const res = await authedFetch(path, { headers: { Accept: "*/*" } });
  if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => null));
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "download";
  return { blob: await res.blob(), filename };
}

/** For the few routes that work before sign-in. Sends no token and no company. */
export async function publicApi<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const res = await fetch(path, { ...init, headers });
  const body: unknown = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, body);
  return body as T;
}
