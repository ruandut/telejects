/**
 * The network layer: the only place in the app that calls fetch. Features build their query and
 * mutation hooks on `api()`.
 */
import { useAuth } from "@/stores/auth";

import { refreshAccessToken } from "./auth";
import { ApiError } from "./errors";

async function authedFetch(path: string, init: RequestInit): Promise<Response> {
  const send = (token: string | null) => {
    const headers = new Headers(init.headers);
    // The browser sets a FormData body's Content-Type itself, including the boundary.
    if (!headers.has("Content-Type") && !(init.body instanceof FormData))
      headers.set("Content-Type", "application/json");
    if (token) headers.set("Authorization", `Bearer ${token}`);
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
  return res;
}

/** fetch() for /api/* with the JWT attached and one transparent refresh on 401. */
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await authedFetch(path, init);
  const body: unknown = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, body);
  return body as T;
}

/** For the few routes that work before sign-in. Sends no token. */
export async function publicApi<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const res = await fetch(path, { ...init, headers });
  const body: unknown = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, body);
  return body as T;
}
