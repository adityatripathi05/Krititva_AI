import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import {
  ACCESS_COOKIE,
  API_BASE,
  API_PREFIX,
  REFRESH_COOKIE,
  REFRESH_MAX_AGE,
} from "@/lib/api/config";

const secure = process.env.NODE_ENV === "production";

interface TokenPair {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

async function forward(
  method: string,
  url: string,
  access: string | undefined,
  body: string | undefined,
): Promise<Response> {
  const headers = new Headers();
  if (access) headers.set("Authorization", `Bearer ${access}`);
  if (body) headers.set("Content-Type", "application/json");
  return fetch(url, { method, headers, body, cache: "no-store" });
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

async function handle(
  request: Request,
  ctx: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await ctx.params;
  const search = new URL(request.url).search;
  const target = `${API_BASE}${API_PREFIX}/${path.join("/")}${search}`;
  const method = request.method;
  const body =
    method === "GET" || method === "HEAD" ? undefined : await request.text();

  const store = await cookies();
  const access = store.get(ACCESS_COOKIE)?.value;

  let res = await forward(method, target, access, body || undefined);

  if (res.status === 401) {
    const refreshed = await tryRefresh(store.get(REFRESH_COOKIE)?.value);
    if (refreshed) {
      store.set(ACCESS_COOKIE, refreshed.access_token, {
        httpOnly: true,
        secure,
        sameSite: "lax",
        path: "/",
        maxAge: refreshed.expires_in,
      });
      store.set(REFRESH_COOKIE, refreshed.refresh_token, {
        httpOnly: true,
        secure,
        sameSite: "lax",
        path: "/",
        maxAge: REFRESH_MAX_AGE,
      });
      res = await forward(method, target, refreshed.access_token, body || undefined);
    }
  }

  const payload = await res.text();
  return new NextResponse(payload, {
    status: res.status,
    headers: {
      "Content-Type": res.headers.get("Content-Type") ?? "application/json",
    },
  });
}

export const GET = handle;
export const POST = handle;
export const PATCH = handle;
export const PUT = handle;
export const DELETE = handle;
