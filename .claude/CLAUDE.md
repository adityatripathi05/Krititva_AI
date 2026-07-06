# Krititva AI — Contributor & Assistant Guardrails

You are working on **Krititva AI**, an open-source (AGPL-3.0), self-hostable project management platform for software agencies. It supports both Waterfall and Agile methodologies per project and integrates a contextual multi-agent AI layer that maintains the SRS → Epics → HLD/LLD → Stories → Tasks → Test Cases chain with end-to-end traceability.

**Source of truth** — always the four `docs/*.md` files, in this precedence:

1. [docs/krititva-srs.md](../docs/krititva-srs.md) — what the system must do (FR/NFR IDs)
2. [docs/krititva-hld.md](../docs/krititva-hld.md) — architecture and module boundaries
3. [docs/krititva-lld.md](../docs/krititva-lld.md) — DDL, service contracts, API surface
4. [docs/krititva-roadmap.md](../docs/krititva-roadmap.md) — milestones and tasks
5. [docs/krititva-ai-blueprint.md](../docs/krititva-ai-blueprint.md) — original blueprint (v0.2), superseded by the above where they conflict

**Rule of precedence when in doubt:** LLD > HLD > SRS > blueprint. Roadmap only decides *when*, not *what*.

---

## 1. Non-negotiable rules (never break these)

These are load-bearing invariants. If a task appears to require breaking one, stop and check with the user.

### 1.1 Draft-and-review is the only path to canonical
- Every AI output persists as a **draft** (`document_versions.status='draft'` or `work_items.ai_generated=TRUE` in a non-canonical state) before any human sees it.
- Nothing an LLM emits mutates canonical project state without an explicit `POST /jobs/{id}/accept` from a human.
- Do not add "auto-apply", "auto-assign", or "auto-move" behaviors, even under a feature flag. Autonomous actions are post-v2.
- SRS anchor: FR-4.6.5, FR-4.6.6.

### 1.2 Provenance is persisted *before* the LLM call
- `ai_provenance` rows are `INSERT`ed and committed **before** `LLMClient.acompletion` is called.
- If the LLM fails, hangs, or crashes, the audit trail exists.
- Do not "optimize" this by batching provenance writes with the completion result.
- SRS anchor: FR-4.6.4.

### 1.3 Immutability at the audit boundary
Append-only tables: `document_versions`, `document_chunks`, `ai_generation_jobs` (after `finished_at`), `ai_provenance`, `milestone_approvals`, `audit_log`, `signed_links`.
- Corrections are new rows, not `UPDATE`s.
- `milestone_approvals` revocation sets `revoked_at`; it does not delete the row.
- `document_versions.status` may transition (`draft → in_review → approved → superseded`) but `content_md`, `content_hash`, and chunks derived from it must never mutate.

### 1.4 404-not-403 for membership disclosure
- A read that finds a resource the caller isn't authorized for returns **404**, not 403.
- Enforce this in service classes, not just at the controller edge.
- SRS anchor: NFR-5.2.8.

### 1.5 Every state-changing operation writes an audit row *in the same transaction*
- Use `AuditSink.write(db, ...)` before `db.commit()`.
- If the write logic is spread across services, the calling handler owns audit composition — do not have `WorkItemService` reach into `DocumentService` to trigger an audit; compose in the route.
- SRS anchor: FR-4.10.1, HLD §7.3.

### 1.6 Zero external calls by default
- `KRITITVA_TELEMETRY_ENABLED=false` is the shipped default and must produce **exactly zero outbound requests** apart from user-initiated LLM calls.
- No CDN references, no fonts pulled from the network, no analytics beacons, no crash reporters.
- SRS anchor: FR-4.12.5, NFR-5.5.2.

### 1.7 AGPL-3.0 compatibility for every dependency
- Before adding any new runtime dependency, verify its license is AGPL-compatible.
- Never bundle LLM weights in the repo or in container images (license-incompatible).
- The CI license-audit job is authoritative; fix a red audit at the dep, not by suppressing the check.
- SRS anchor: NFR-5.6.1–5.6.3.

### 1.8 Methodology is data, not code
- Agile vs. Waterfall vs. Hybrid differences live in `workflow_states`, `workflow_transitions`, `hierarchy_rules`, and JSON seeds under `packages/methodology-templates/`.
- Never write `if methodology == 'waterfall': ...` in service code. If the engine needs to branch, express it as a data query.
- SRS anchor: FR-4.3.*, HLD §3.

### 1.9 `organization_id` is populated on every tenant-scoped write
- Even though the column is nullable in v1, always populate it on `INSERT`. This is what makes the future multi-tenant migration a backfill instead of a rewrite.
- SRS anchor: FR-4.1.3, HLD §4.1.

### 1.10 Structured output enforcement is a security control
- LLM calls always pass `response_format=<PydanticModel>` through the gateway.
- Application layer validates with `model_validate_json` and **drops unknown fields**.
- No field-name in an LLM output may drive account/config mutation. If a new capability seems to require it, escalate.
- SRS anchor: NFR-5.2.6, HLD §6.5.

---

## 2. Tech stack (definitive)

Backend
- Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, Pydantic v2, pydantic-settings
- arq for job queue, Redis 7 as backing store
- LiteLLM as the LLM gateway
- Ollama as default local runtime; `nomic-embed-text` v1.5 as default embedder
- Argon2id for password hashing; Authlib for OIDC
- Package management: **uv**

Frontend
- Next.js 15 (App Router), TypeScript strict
- shadcn/ui, TipTap, Mermaid.js, dnd-kit
- TanStack Query + minimal Zustand
- Package management: **pnpm** in a Turborepo workspace

Database
- PostgreSQL 16 + pgvector + pgcrypto + citext
- HNSW indexes with `m=16, ef_construction=64`
- Advisory lock at Alembic upgrade start: `SELECT pg_advisory_lock(hashtext('krititva-migrations'))`

Observability
- Prometheus `/metrics`
- Langfuse (self-hosted, opt-in via compose profile `obs`)
- Structured JSON logs with correlation IDs

Rejected: Django, Celery, Weaviate/Qdrant, Prisma. Don't propose them again without a strong reason and a corresponding LLD update.

---

## 3. Repository layout

Follow [krititva-lld.md §1](../docs/krititva-lld.md) exactly. Do not invent new top-level dirs without updating the LLD first.

```
apps/web/                Next.js
apps/api/app/            FastAPI + workers + ai/
packages/methodology-templates/    Seed JSON
packages/api-client/     Generated from OpenAPI
deploy/                  docker-compose.yml, litellm.config.yaml, nginx.conf
docs/                    The four spec docs
.planning/               GSD workflow state (already used in this repo)
```

---

## 4. Coding conventions

### 4.1 Python (backend)
- `mypy --strict` MUST pass. Never `# type: ignore` without a comment explaining why.
- `ruff` with the project's ruleset MUST pass; treat warnings as errors in CI.
- Async everywhere in the API path. Sync-only libs are wrapped with `run_in_executor` at the boundary.
- Services take `AsyncSession` and `AuditSink` in `__init__` (see [LLD §3.1](../docs/krititva-lld.md)).
- **One request → one session → many services.** Do not open a second session inside a request handler.
- **Workers open their own session per job.** Do not share sessions across arq calls.
- Raise typed exceptions from `app/api/errors.py`; do NOT raise raw `HTTPException` in service layers.
- Never write `time.sleep`; use `asyncio.sleep`.
- No f-strings inside SQL. Use SQLAlchemy bindings or `text(":x")`.

### 4.2 TypeScript (frontend)
- `tsc --noEmit` and `eslint` MUST pass with zero warnings.
- No `any`. Use generated types from `packages/api-client`.
- Server-state via TanStack Query; UI-local flags via minimal Zustand stores. **No Redux.**
- Optimistic mutations only for local-visible transitions (board drag, rank). Roll back on 4xx and toast the error code from the response.
- No inline styles for spacing/layout — use Tailwind via shadcn tokens.

### 4.3 Comments and docstrings
- Default to writing no comments. Names, types, and small functions should tell the story.
- If a comment is warranted, explain **why**, not **what**.
- No PR-scoped comments in code (`// added for #123`, `# handles the case from the demo`).
- Multi-line docstrings only on public interfaces (`RoleProfile`, exported service methods).

---

## 5. Testing

- Test doubles for LLMs use `FakeLLMClient` (fixture-backed). Real Ollama is only invoked in the tagged-release smoke suite; never in unit/PR CI.
- Postgres is real in integration tests (testcontainers). No SQLite-substitution.
- Transactional test isolation: `SAVEPOINT` per test, rollback on teardown.
- Coverage floors: engine 90% line, state machine 100% branch, approval quorum 100% branch, context assembler 90% line.
- Property-based tests (Hypothesis) for lexorank, chunk packing, and quorum evaluation.
- Playwright E2E hits the docker-compose stack on `main` only.

---

## 6. Migrations

Use the `krititva-migration` skill for every Alembic migration. Non-negotiables:

1. Advisory lock at upgrade start.
2. Enums created before the tables that reference them.
3. Deferred FK constraints for the two known cycles (`documents ↔ document_versions`, `work_items ↔ ai_generation_jobs`).
4. `organization_id UUID NULL` on every new tenant-scoped table (populated on INSERT even in v1).
5. HNSW indexes as partial (`WHERE embedding IS NOT NULL`).
6. Never modify a shipped migration — write a new one.
7. Every migration must have a working `downgrade` OR a changelog entry flagging it irreversible.

---

## 7. AI role profiles

Every agent is data, not code. To add or modify one, use the `krititva-role-profile` skill. Non-negotiables:

1. `output_schema` is a Pydantic model; the LLM cannot emit fields outside it.
2. `retrieval_policy` returns a `RetrievalPlan`; the Context Assembler is the only path to context — never fetch chunks ad-hoc inside a profile.
3. `persist_draft` writes `status='draft'` (documents) or `ai_generated=TRUE` in the project's initial state (work items). It never approves.
4. New profiles register via the `krititva.agents` entry-point group; core code does not import them by module path.
5. Prompts wrap doc chunks in delimited blocks and instruct the model to ignore embedded instructions.

---

## 8. Working with the roadmap

- Each milestone task in [krititva-roadmap.md](../docs/krititva-roadmap.md) has an ID like `M0.T3.4` and cites SRS FR/NFR anchors.
- When implementing a task: read the task, read the cited SRS anchors, read the cited LLD section, then plan. Do not implement from the task title alone.
- Break a task into commits by subtask (`M0.T3.4`) where feasible; each commit's message references the task and the primary SRS anchor.
- If the plan diverges from the LLD, update the LLD in the same PR — do not let code and spec drift.

---

## 9. Commit and PR conventions

- Conventional-style prefix: `feat(scope): ...`, `fix(scope): ...`, `chore(scope): ...`, `docs(scope): ...`, `test(scope): ...`.
- `scope` is a module or milestone task ID: `feat(work-items): enforce hard gates (M2.T4.4, FR-4.7.4)`.
- DCO sign-off required (`Signed-off-by:`).
- Never `--no-verify` on hooks. Never `--amend` a pushed commit.
- PR body links to the roadmap task, lists the FR/NFR anchors implemented, and calls out any LLD deltas.

---

## 10. Security posture (must-do checks)

- Argon2id params meet §NFR-5.2.1 baselines.
- No secret in code, env-in-tree, or logs. Provider keys and IdP secrets encrypted at rest with `KRITITVA_DATA_KEY`.
- CSRF middleware on state-changing endpoints for browser sessions.
- Every LLM output path: schema-strict validation + unknown-field drop.
- Every embedding-touching backup/export path treats vector columns with the same controls as source content (§NFR-5.2.7).
- Rate limits enforced per-org (RPS) and per-user (AI concurrency).

---

## 11. Skills you should use

Prefer the project skills over ad-hoc work. Each is in `.claude/skills/`.

- `krititva-scaffold-module` — new API module (route + service + Pydantic schemas + tests) following our patterns.
- `krititva-migration` — Alembic migration with the rules above.
- `krititva-role-profile` — new AI role profile with retrieval policy + prompts + schema + persist.
- `krititva-verify-traceability` — check that new code carries an FR/NFR anchor referenced somewhere.

---

## 12. Things NOT to do (common failure modes)

- Do not add a "quick regenerate" auto-loop on stale-flag detection. Stale flags surface to humans; humans decide.
- Do not add a CRDT / WebSocket collab layer to documents (v2).
- Do not add per-user AI training or feedback fine-tuning (out of scope; also complicates local-only story).
- Do not swap the OpenAPI-first API client for a hand-written one.
- Do not introduce a second ORM or a second migration tool.
- Do not add cloud-specific SDKs (AWS/GCP/Azure) to `apps/api` core — storage adapters go behind an interface with the filesystem impl as default.
- Do not weaken the "no phone-home" default under any circumstances, even for "just crash reports."

---

## 13. Personal working notes

- User is `Aditya Tripathi` <aditya.tripathi@echelonedge.com>, driving this as a self-directed project (path: `SelfDev/Krititva_AI`).
- User wrote the original blueprint and delegates the deep architect work; they read the specs and expect concrete deliverables, not open-ended surveys.
- Prefer to produce artifacts (docs, schemas, code) over paragraphs of prose.

---

## 14. When to stop and ask

Stop and confirm with the user before:

- Adding a new top-level directory outside the LLD layout.
- Adding a runtime dependency whose license needs review.
- Changing a v1-scope decision (SRS §1.2 in-scope vs. deferred).
- Weakening or removing any of the ten non-negotiables in §1.
- Refactoring across more than two modules in one PR.
- Any destructive git operation on `main` or on branches with unpushed work.
