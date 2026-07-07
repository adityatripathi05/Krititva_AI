/** Server-only API config. Never import from a client component. */

export const API_BASE = process.env.KRITITVA_API_URL ?? "http://localhost:8000";
export const API_PREFIX = "/api/v1";

export const ACCESS_COOKIE = "krititva_access";
export const REFRESH_COOKIE = "krititva_refresh";

export const REFRESH_MAX_AGE = 60 * 60 * 24 * 14; // 14 days, mirrors backend refresh TTL
