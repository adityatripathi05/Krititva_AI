# @krititva/web

Next.js 15 App Router client for Krititva AI. See root [README](../../README.md) and specs in [`docs/`](../../docs/).

## Local dev

```bash
# From repo root
pnpm install
pnpm --filter @krititva/web dev
```

Point at a different API host with `NEXT_PUBLIC_API_URL=http://api.local:8000 pnpm --filter @krititva/web dev`.

## shadcn/ui

Base tokens are pre-wired (`app/globals.css`, `tailwind.config.ts`). To add a component:

```bash
pnpm dlx shadcn@latest add button
```

Components are added under `components/ui/`.

## Rules

Contributor guardrails: [.claude/CLAUDE.md](../../.claude/CLAUDE.md) §4.2. Highlights: `tsc --noEmit` and `eslint` must pass with zero warnings; no `any`; use the generated API client from `@krititva/api-client`; no Redux.
