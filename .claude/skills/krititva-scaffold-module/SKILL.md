---
name: krititva-scaffold-module
description: Scaffold a new backend module in apps/api/app/ following Krititva's route→service→schema→test pattern. Use when adding a new resource (e.g. sprints, milestones, capacity) that isn't yet in the codebase.
---

# krititva-scaffold-module

Scaffold a backend module following the LLD §1 and §3 patterns. Never invent a layout; match the existing modules.

## Inputs
Ask the user (or infer from the task ID they cite) for:
- Module name (singular, snake_case). Example: `sprint`, `milestone`, `capacity_entry`.
- Table name (plural). Example: `sprints`.
- SRS anchor(s) it delivers. Example: `FR-4.8.1–4.8.5`.
- Roadmap task ID. Example: `M3.T1`.

## Files to create

1. `apps/api/app/models/<module>.py` — SQLAlchemy ORM class matching the DDL in `docs/krititva-lld.md §2.2`.
2. `apps/api/app/schemas/<module>.py` — Pydantic v2 request/response schemas.
3. `apps/api/app/services/<module>.py` — Service class with `__init__(db: AsyncSession, audit: AuditSink)`.
4. `apps/api/app/api/routes/<module>.py` — FastAPI router mounted under `/projects/{project_id}/<plural>` (or top-level where LLD §4 says otherwise).
5. `apps/api/tests/services/test_<module>.py` — unit tests.
6. `apps/api/tests/api/test_<module>_routes.py` — endpoint tests using the transactional client fixture.

## Rules to bake in

- Route handlers call `require_project_role(...)` (or the closest specific decorator) and pass `db` + `user` into the service constructor.
- Service methods that mutate state call `audit.write(...)` **before** `db.commit()`.
- Service methods raise typed exceptions from `app/api/errors.py`. Never raise `HTTPException` from a service.
- Reads that hit a resource the caller isn't authorized for raise `NotFound`, mapped to 404 (§NFR-5.2.8).
- Every `INSERT` populates `organization_id` from the resolved project.
- Route file exports one `router: APIRouter` — the main app mounts it in `apps/api/app/main.py`.

## Test scaffolding

- Use the shared `client` fixture (async httpx client bound to the app).
- Use the shared `db_session` fixture (SAVEPOINT-per-test).
- Use `FakeLLMClient` from `tests/fakes/llm.py` when any AI path is touched.
- Cover: happy path, 404 on cross-org, 403 on wrong role, 422 on schema violation, 409 on the module's specific state conflict (if any).

## After scaffolding

1. Run `uv run ruff check apps/api/app/` and `uv run mypy apps/api/app/`.
2. Run `uv run pytest apps/api/tests/services/test_<module>.py apps/api/tests/api/test_<module>_routes.py`.
3. Regenerate the API client: `pnpm --filter api-client generate`.
4. In the PR body, cite the SRS anchor(s) and roadmap task ID.

## Don't

- Don't create SQLAlchemy sessions inside the service methods; the constructor receives one.
- Don't create a second audit writer; use `AuditSink`.
- Don't share request-scoped state between services via module-level globals.
- Don't put business logic in the route handler beyond auth + service call + response shaping.
