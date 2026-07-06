# krititva-api

FastAPI backend for Krititva AI. See the root [README](../../README.md) and the specs in [`docs/`](../../docs/) for context.

## Local dev

```bash
# From repo root
uv sync --project apps/api

# Run the API
uv run --project apps/api uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run the arq worker
uv run --project apps/api arq app.workers.arq_settings.WorkerSettings

# Lint + type-check + test
uv run --project apps/api ruff check app tests
uv run --project apps/api mypy app
uv run --project apps/api pytest
```

## Migrations

```bash
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
uv run --project apps/api alembic -c apps/api/alembic.ini downgrade -1
```

Use the `krititva-migration` skill to author new revisions — do NOT use `--autogenerate`. See [.claude/skills/krititva-migration/SKILL.md](../../.claude/skills/krititva-migration/SKILL.md).

## Layout

Follows [`docs/krititva-lld.md §1`](../../docs/krititva-lld.md). Non-negotiable coding guardrails are in [.claude/CLAUDE.md](../../.claude/CLAUDE.md).
