"""Double-submit CSRF middleware (NFR-5.2.9).

Contract:
- Every response sets a CSRF cookie (``settings.csrf_cookie_name``) if absent.
  Value: a URL-safe opaque token; ``SameSite=Lax``; ``HttpOnly=False`` (readable
  by the SPA so it can echo it into the header).
- State-changing requests (POST/PUT/PATCH/DELETE) MUST present the same value
  in ``settings.csrf_header_name``; mismatch → 403 ``csrf_mismatch``.

Bearer-authenticated API clients that do NOT carry a session cookie are
exempted — CSRF only applies to browser-session requests.
"""

from __future__ import annotations

import secrets
from typing import Final

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import get_settings

STATE_CHANGING: Final = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Auth entry points that establish a session and are already authenticated by
# credentials or a one-time token carried in the request body — CSRF doesn't
# apply because the body-carried secret is the security boundary.
CSRF_EXEMPT_SUFFIXES: Final = (
    "/auth/login",
    "/auth/refresh",
    "/auth/invitations/accept",
    "/auth/setup",
)


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        s = get_settings()
        cookie_name = s.csrf_cookie_name
        header_name = s.csrf_header_name
        cookie_value = request.cookies.get(cookie_name)

        # Enforce only when the client already has a CSRF cookie (established
        # session), is NOT using Bearer auth, and is NOT hitting an auth entry
        # point that carries its own body-scoped secret.
        if (
            request.method in STATE_CHANGING
            and cookie_value
            and not _has_bearer(request)
            and not _is_exempt(request.url.path)
        ):
            supplied = request.headers.get(header_name)
            if not supplied or not secrets.compare_digest(cookie_value, supplied):
                return JSONResponse(
                    status_code=403,
                    content={"code": "csrf_mismatch"},
                )

        response = await call_next(request)

        if not cookie_value:
            response.set_cookie(
                key=cookie_name,
                value=secrets.token_urlsafe(24),
                httponly=False,
                samesite="lax",
                secure=s.environment == "production",
                path="/",
            )
        return response


def _has_bearer(request: Request) -> bool:
    return request.headers.get("Authorization", "").lower().startswith("bearer ")


def _is_exempt(path: str) -> bool:
    return any(path.endswith(suffix) for suffix in CSRF_EXEMPT_SUFFIXES)
