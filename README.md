# Krititva AI

**Open-source, self-hostable project management for software agencies.** Dual Waterfall/Agile per project. A contextual multi-agent AI layer maintains the SRS → Epics → HLD/LLD → Stories → Tasks → Test Cases chain with end-to-end traceability.

- **License:** AGPL-3.0-only
- **Default deployment:** fully local (Ollama + pgvector); zero external calls
- **Status:** pre-alpha — building toward M0 Foundation

## Quick links

- Specification: [`docs/krititva-srs.md`](docs/krititva-srs.md)
- Architecture: [`docs/krititva-hld.md`](docs/krititva-hld.md), [`docs/krititva-lld.md`](docs/krititva-lld.md)
- Roadmap: [`docs/krititva-roadmap.md`](docs/krititva-roadmap.md)
- Contributor guide: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Security disclosure: [`SECURITY.md`](SECURITY.md)

## Repository layout

```
apps/web/                  Next.js 15 web client
apps/api/                  FastAPI backend + arq workers + AI subsystem
packages/methodology-templates/    Agile / Waterfall / Hybrid seed JSON
packages/api-client/       TypeScript client generated from OpenAPI
deploy/                    docker-compose.yml, litellm.config.yaml, nginx.conf
docs/                      SRS, HLD, LLD, roadmap
.claude/                   Contributor / assistant guardrails
```

## Prerequisites

- Node 20.11+ and pnpm 9+
- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Docker Engine 24+ and Docker Compose v2
- (Optional) an Ollama installation with `nomic-embed-text` and one generation model pulled

## Local development

```bash
# Install workspace dependencies
pnpm install

# Backend dependencies
uv sync --project apps/api

# Start the stack (dev-mode: postgres, redis, litellm; web + api run outside compose)
docker compose --file deploy/docker-compose.yml up postgres redis litellm -d

# Backend
uv run --project apps/api uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (in another shell)
pnpm --filter web dev
```

## Self-host quickstart

A fresh install in five steps. Everything runs locally; with telemetry off (the
default) the instance makes **zero outbound requests** apart from your own LLM calls.

```bash
# 1. Configure. Copy the example env and set at least KRITITVA_JWT_SECRET and
#    KRITITVA_DATA_KEY (a 32-byte base64 value). Telemetry stays off by default.
cp .env.example .env

# 2. Bring up the full stack (web, api, worker, postgres+pgvector, redis, litellm).
#    `--env-file .env` is required: with `-f deploy/...` compose reads .env from
#    the file's directory, not the repo root. `--build` builds the local images.
docker compose -f deploy/docker-compose.yml --env-file .env up -d --build
#    (add `--profile obs` to also start self-hosted Langfuse)
```

Migrations run automatically at api start, serialized by an advisory lock so
multiple api replicas don't race; a failed migration halts startup with a clear
error (FR-4.12.4).

3. **First-run setup.** Open `http://localhost:3000`. With no admin yet you're
   sent to **`/setup`** — create your organization and the first `org_admin`. This
   door closes the moment an admin exists (a second `POST /auth/setup` returns
   `409 already_bootstrapped`).

4. **Invite your team, then work.** Sign in, invite users, create an Agile
   project (the methodology template seeds its board, transitions, and hierarchy),
   add work items, and drag them across the board — every change writes an audit row.

5. **Back up.** The `krititva` CLI wraps the documented `pg_dump -Fc` procedure and
   copies uploaded assets:

   ```bash
   # Inside the api container (or any env with the package + POSTGRES_DSN set):
   krititva backup --output /backups/krititva-$(date +%F).dump
   krititva restore /backups/krititva-2026-07-07.dump
   krititva --print-only backup      # print the exact commands without running them
   ```

   Schedule step 5 with cron and keep the dumps off-box; that's your DR story.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). All commits require a DCO sign-off (`git commit -s`).

## Support

- File an issue for bugs or feature requests.
- Security vulnerabilities: see [`SECURITY.md`](SECURITY.md).
