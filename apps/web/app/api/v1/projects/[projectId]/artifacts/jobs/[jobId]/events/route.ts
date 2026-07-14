import { cookies } from "next/headers";

import {
  ACCESS_COOKIE,
  API_BASE,
  API_PREFIX,
  REFRESH_COOKIE,
  REFRESH_MAX_AGE,
} from "@/lib/api/config";

// The catch-all BFF proxy (`app/api/v1/[...path]`) buffers the full upstream body
// (`await res.text()`), which would defeat SSE. This dedicated leaf route shadows
// the catch-all only for the events path and pipes the upstream `text/event-stream`
// ReadableStream straight through, unbuffered. `force-dynamic` + the no-cache/
// no-transform headers keep Next and any intermediary from buffering the stream.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const secure = process.env.NODE_ENV === "production";

interface TokenPair {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

async function tryRefresh(refresh: string | undefined): Promise<TokenPair | null> {
  if (!refresh) return null;
  const res = await fetch(`${API_BASE}${API_PREFIX}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
    cache: "no-store",
  });
  if (!res.ok) return null;
  return (await res.json()) as TokenPair;
}

function streamHeaders(extra?: Headers): Headers {
  const headers = extra ?? new Headers();
  headers.set("Content-Type", "text/event-stream");
  headers.set("Cache-Control", "no-cache, no-transform");
  headers.set("Connection", "keep-alive");
  headers.set("X-Accel-Buffering", "no");
  return headers;
}

export async function GET(
  request: Request,
  ctx: { params: Promise<{ projectId: string; jobId: string }> },
): Promise<Response> {
  const { projectId, jobId } = await ctx.params;
  const target = `${API_BASE}${API_PREFIX}/projects/${projectId}/artifacts/jobs/${jobId}/events`;

  const store = await cookies();
  const access = store.get(ACCESS_COOKIE)?.value;

  const open = (token: string | undefined) =>
    fetch(target, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      cache: "no-store",
      signal: request.signal,
    });

  let upstream = await open(access);
  const setCookies = new Headers();

  if (upstream.status === 401) {
    const refreshed = await tryRefresh(store.get(REFRESH_COOKIE)?.value);
    if (refreshed) {
      const cookieOpts = "; HttpOnly; SameSite=Lax; Path=/" + (secure ? "; Secure" : "");
      setCookies.append(
        "Set-Cookie",
        `${ACCESS_COOKIE}=${refreshed.access_token}; Max-Age=${refreshed.expires_in}${cookieOpts}`,
      );
      setCookies.append(
        "Set-Cookie",
        `${REFRESH_COOKIE}=${refreshed.refresh_token}; Max-Age=${REFRESH_MAX_AGE}${cookieOpts}`,
      );
      upstream = await open(refreshed.access_token);
    }
  }

  if (!upstream.ok || upstream.body === null) {
    // Surface the auth/permission failure so EventSource's onerror fires and the
    // client falls back to polling rather than hanging on a dead stream.
    return new Response(null, { status: upstream.status });
  }

  const headers = streamHeaders(setCookies);
  return new Response(upstream.body, { status: 200, headers });
}
