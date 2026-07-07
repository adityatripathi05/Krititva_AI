import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { ACCESS_COOKIE, API_BASE, API_PREFIX } from "./config";
import type { ApiError } from "./types";

export class ServerApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: ApiError | null,
  ) {
    super(body?.code ?? `http_${status}`);
    this.name = "ServerApiError";
  }
}

/**
 * Fetch the backend from a Server Component / Route Handler, attaching the
 * caller's access token from the HTTP-only cookie as a Bearer header. Bearer
 * auth bypasses CSRF on the backend, so no token juggling is needed.
 */
export async function serverApi<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const store = await cookies();
  const access = store.get(ACCESS_COOKIE)?.value;
  const headers = new Headers(init.headers);
  if (access) {
    headers.set("Authorization", `Bearer ${access}`);
  }
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${API_BASE}${API_PREFIX}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });

  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as ApiError | null;
    throw new ServerApiError(res.status, body);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

/**
 * Like ``serverApi`` but treats an auth failure as an expired session: a 401/403
 * redirects to ``/login`` instead of crashing the page. Server Components can't
 * refresh cookies, so re-auth is the correct recovery. Use this in every
 * authenticated ``(app)`` page/layout; ``serverApi`` stays for public calls.
 */
export async function serverApiAuthed<T>(path: string, init: RequestInit = {}): Promise<T> {
  try {
    return await serverApi<T>(path, init);
  } catch (err) {
    if (err instanceof ServerApiError && (err.status === 401 || err.status === 403)) {
      redirect("/login");
    }
    throw err;
  }
}
