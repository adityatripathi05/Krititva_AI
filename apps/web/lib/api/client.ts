"use client";

import type { ApiError } from "./types";

export class ClientApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly body: ApiError | null,
  ) {
    super(code);
    this.name = "ClientApiError";
  }
}

/**
 * Browser fetch that goes through the same-origin BFF proxy (`/api/v1/*`),
 * which attaches the Bearer token from the HTTP-only cookie. The proxy — not
 * the browser — holds the credential, so the token is never exposed to JS.
 */
export async function clientApi<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`/api/v1${path}`, {
    ...init,
    headers,
    credentials: "same-origin",
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as ApiError | null;
    throw new ClientApiError(res.status, body?.code ?? `http_${res.status}`, body);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}
