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
  const body = (await request.json().catch(() => null)) as {
    email?: string;
    password?: string;
  } | null;
  if (!body?.email || !body?.password) {
    return NextResponse.json({ code: "invalid_request" }, { status: 400 });
  }

  const res = await fetch(`${API_BASE}${API_PREFIX}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: body.email, password: body.password }),
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ code: "invalid_credentials" }));
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
