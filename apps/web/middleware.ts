import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { ACCESS_COOKIE, REFRESH_COOKIE } from "@/lib/api/config";

/**
 * Gate the authenticated app. A presence check on the session cookies is enough
 * for routing UX — the backend enforces real authorization on every request.
 * An access cookie may have expired while the refresh cookie is still valid, so
 * either cookie is treated as "has a session"; the proxy refreshes on demand.
 */
export function middleware(request: NextRequest): NextResponse {
  const hasSession =
    request.cookies.has(ACCESS_COOKIE) || request.cookies.has(REFRESH_COOKIE);
  if (!hasSession) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", request.nextUrl.pathname);
    return NextResponse.redirect(login);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard", "/dashboard/:path*", "/projects", "/projects/:path*"],
};
