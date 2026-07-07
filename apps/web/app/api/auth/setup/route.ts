import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import {
  ACCESS_COOKIE,
  API_BASE,
  API_PREFIX,
  REFRESH_COOKIE,
  REFRESH_MAX_AGE,
} from "@/lib/api/config";

interface TokenPair {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

const secure = process.env.NODE_ENV === "production";

export async function POST(request: Request): Promise<NextResponse> {
  const body = await request.text();
  const res = await fetch(`${API_BASE}${API_PREFIX}/auth/setup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ code: "setup_failed" }));
    return NextResponse.json(err, { status: res.status });
  }

  const tokens = (await res.json()) as TokenPair;
  const store = await cookies();
  store.set(ACCESS_COOKIE, tokens.access_token, {
    httpOnly: true,
    secure,
    sameSite: "lax",
    path: "/",
    maxAge: tokens.expires_in,
  });
  store.set(REFRESH_COOKIE, tokens.refresh_token, {
    httpOnly: true,
    secure,
    sameSite: "lax",
    path: "/",
    maxAge: REFRESH_MAX_AGE,
  });
  return NextResponse.json({ ok: true });
}
