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

Full self-host quickstart lands with milestone M0.T7. See [`docs/krititva-roadmap.md`](docs/krititva-roadmap.md).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). All commits require a DCO sign-off (`git commit -s`).

## Support

- File an issue for bugs or feature requests.
- Security vulnerabilities: see [`SECURITY.md`](SECURITY.md).
