import path from "node:path";

import type { NextConfig } from "next";

// Standalone output is only needed for the Docker runtime image, and its symlink
// step fails on Windows without Developer Mode. Gate it behind an env flag the
// Dockerfile sets, so local `pnpm build` stays a plain, cross-platform build.
const standalone = process.env.BUILD_STANDALONE === "1";

const config: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // No phone-home. See .claude/CLAUDE.md §1.6.
  productionBrowserSourceMaps: false,
  typedRoutes: true,
  // The backend is reached through the BFF route handlers under app/api/* (they
  // attach the Bearer token from the HTTP-only cookie), not a rewrite — a plain
  // rewrite cannot inject the credential the backend requires.
  ...(standalone
    ? {
        output: "standalone" as const,
        // Trace from the monorepo root so pnpm-workspace deps land in the bundle.
        outputFileTracingRoot: path.resolve(process.cwd(), "../.."),
      }
    : {}),
};

export default config;
