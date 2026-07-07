import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // No phone-home. See .claude/CLAUDE.md §1.6.
  productionBrowserSourceMaps: false,
  typedRoutes: true,
  // The backend is reached through the BFF route handlers under app/api/* (they
  // attach the Bearer token from the HTTP-only cookie), not a rewrite — a plain
  // rewrite cannot inject the credential the backend requires.
};

export default config;
