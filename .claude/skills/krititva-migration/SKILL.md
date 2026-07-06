---
name: krititva-migration
description: Create an Alembic migration for Krititva AI with the project's mandatory rules (advisory lock, enum ordering, deferred FKs, organization_id nullable). Use whenever the schema changes.
---

# krititva-migration

Create a new Alembic migration for `apps/api/`. Never modify a shipped migration — write a new one on top.

## Inputs
- Change description (one line, imperative).
- Roadmap task ID and SRS/LLD anchors driving the change.
- Whether the change is reversible.

## Steps

1. **Generate the migration file.**
   ```bash
   uv run alembic -c apps/api/alembic.ini revision -m "<slug>"
   ```
   Do NOT use `--autogenerate` — the schema is source-of-truth in `docs/krititva-lld.md §2.2`; autogenerate drifts from that.

2. **Structure the migration file.**
   - Docstring first line = concise change description.
   - Body lists SRS/LLD anchors as a comment block above `upgrade()`.
   - `upgrade()` follows the ordering rules below.
   - `downgrade()` is the exact inverse OR raises `NotImplementedError("irreversible")` with a changelog line added to `docs/CHANGELOG.md`.

3. **Ordering rules inside `upgrade()`.**
   - Enum creation FIRST (`CREATE TYPE`).
   - Tables that reference enums next.
   - Circular FK cases: create both tables without the offending FK, then `ALTER TABLE ... ADD CONSTRAINT` at the end.
   - Indexes last, including HNSW partial indexes for vector columns.
   - Never re-run enum creations; guard with `DO $$ ... EXCEPTION WHEN duplicate_object THEN NULL; END $$;` when appending values to an existing enum in a later migration.

4. **Mandatory column policies.**
   - Every new tenant-scoped table gets `organization_id UUID NULL REFERENCES organizations(id)`. Nullable in v1 by policy; do NOT add `NOT NULL` yet.
   - Every table that will be user-visible gets `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`.
   - Append-only tables (see CLAUDE.md §1.3) get no `updated_at` column at all — presence of `updated_at` is a signal the table is mutable.

5. **Vector column policies.**
   - Primary embedding: `embedding vector(768)` + `embedding_model TEXT`.
   - Optional alt: `embedding_alt vector(1536)` + `embedding_alt_model TEXT`.
   - HNSW index: `USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64) WHERE embedding IS NOT NULL`.

6. **Advisory lock is applied by the startup wrapper**, not inside individual migrations. Do not add `pg_advisory_lock` calls inside `upgrade()`.

## Verify

```bash
uv run alembic -c apps/api/alembic.ini upgrade head        # apply
uv run alembic -c apps/api/alembic.ini downgrade -1        # reverse (if reversible)
uv run alembic -c apps/api/alembic.ini upgrade head        # re-apply
uv run pytest apps/api/tests/migrations/                    # integration test
```

The `test_migrations` suite spins up a fresh Postgres, applies all revisions in order, dumps the schema, and diffs against `docs/krititva-lld.md §2.2`. A drift is a failing test.

## Don't

- Don't drop columns that hold data without a data-preserving copy step.
- Don't rename tables (breaks Langfuse dashboards, external reports). Deprecate + new table + view alias if needed.
- Don't add DB triggers unless the LLD explicitly says so. Business rules live in services, not triggers.
