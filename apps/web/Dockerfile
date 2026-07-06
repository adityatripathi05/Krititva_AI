# Frontend image. Standalone Next.js output for a small runtime layer.
# Finalized in M0.T7.

# --- deps ------------------------------------------------------
FROM node:20-alpine AS deps
RUN corepack enable && corepack prepare pnpm@9.12.0 --activate
WORKDIR /repo
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml turbo.json ./
COPY apps/web/package.json apps/web/package.json
COPY packages ./packages
RUN pnpm install --frozen-lockfile

# --- build -----------------------------------------------------
FROM node:20-alpine AS builder
RUN corepack enable && corepack prepare pnpm@9.12.0 --activate
WORKDIR /repo
COPY --from=deps /repo /repo
COPY apps/web ./apps/web
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm --filter @krititva/web build

# --- runtime ---------------------------------------------------
FROM node:20-alpine AS runtime
RUN adduser -D -u 1000 krititva
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

COPY --from=builder --chown=krititva:krititva /repo/apps/web/.next/standalone ./
COPY --from=builder --chown=krititva:krititva /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder --chown=krititva:krititva /repo/apps/web/public ./apps/web/public

USER krititva
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
