# Krititva AI — M0 Foundation Completion Report

**Status:** M0.T1–M0.T7 delivered — **M0 Foundation complete**
**Upstream:** [krititva-roadmap.md](krititva-roadmap.md), [krititva-lld.md](krititva-lld.md)
**Date range:** 2026-07-06 → 2026-07-07

> §§1–8 cover M0.T1–T3; [§9](#9-m0t4--projects-clients-methodology-config) M0.T4; [§10](#10-m0t5--work-item-engine-core) M0.T5; [§11](#11-m0t6--frontend-shell) M0.T6; [§12](#12-m0t7--bootstrap--operator-experience) M0.T7.

This document tracks what was actually delivered against the roadmap, what was intentionally deferred, and what carries a known caveat or gotcha. It is the source of truth for "what is done vs. what still needs doing" through M0.T3.

---

## 1. Headline metrics

| Metric | Value |
|---|---|
| Files created / modified | ~85 across `apps/`, `packages/`, `deploy/`, `docs/`, `.claude/`, `.github/` |
| Python source files under `mypy --strict` | 35 |
| Test count passing | **52 / 52** |
| Unit tests | 14 (hashing 6 + JWT 7 + health 1) |
| Integration tests | 38 (bootstrap 4 + migrations 3 + roundtrip 4 + login 4 + refresh 4 + logout/me 4 + invitations 4 + csrf 4 + rbac 7) |
| CI workflows in `.github/workflows/` | 3 (ci, license-audit, dco) + dependabot |
| Alembic migrations applied | 4 (001 enums+ext, 002 identity+tenancy, 003 refresh_tokens, 004 audit_log) |
| Postgres tables in schema | 8 (organizations, users, invitations, clients, projects, project_members, refresh_tokens, audit_log) + alembic_version |
| Endpoints live | `/livez`, `/readyz`, `/api/v1/auth/{login,refresh,logout,me,invitations,invitations/accept}` |

---

## 2. Subtask-by-subtask delivery

Legend: ✅ delivered · ⚠️ delivered with caveat · ⏸ deferred (roadmap-sanctioned) · ➕ delivered beyond scope

### M0.T1 — Repo bootstrap and tooling

| Subtask | Status | Notes |
|---|---|---|
| M0.T1.1 Turborepo + pnpm workspace | ✅ | `pnpm-workspace.yaml` is the source of truth; the redundant `workspaces` field in `package.json` was removed during setup |
| M0.T1.2 `apps/api` uv + Python 3.12 + FastAPI + SQLAlchemy 2.0 | ✅ | All deps pinned in `pyproject.toml`; ruff + mypy --strict + pytest configs live |
| M0.T1.3 `apps/web` Next.js 15 + shadcn/ui | ✅ | Pin widened from `15.0.3` to `^15.1.0` to match React 19 GA (15.0.3 predates GA) |
| M0.T1.4 GitHub Actions (ruff, mypy, pytest, eslint, tsc, OpenAPI diff placeholder, license audit) | ⚠️ | OpenAPI diff is a placeholder job as specified; traceability job runs but only warns (not blocking) during pre-alpha |
| M0.T1.5 `docker-compose.yml` structural stack | ✅ | web, api, worker, postgres+pgvector, redis, litellm; langfuse under `--profile obs` |
| M0.T1.6 DCO check + CONTRIBUTING | ✅ | `dco.yml` workflow enforces sign-off on every PR commit; CONTRIBUTING + SECURITY + CODE_OF_CONDUCT committed |
| ➕ `packages/methodology-templates/` | ➕ | Not on the T1 list but scaffolded early — agile/waterfall/hybrid JSON + JSON Schema validator; used by M0.T4 |
| ➕ `packages/api-client/` | ➕ | Workspace-resolvable placeholder so `@krititva/web` can import it; real codegen wires up in M1.T3 |

### M0.T2 — Database + migrations foundation

| Subtask | Status | Notes |
|---|---|---|
| M0.T2.1 Alembic init; advisory-lock startup wrapper | ✅ | Note: switched from session-scoped `pg_advisory_lock` to transaction-scoped `pg_advisory_xact_lock` inside `context.begin_transaction()`. Auto-released on COMMIT/ROLLBACK; avoids finally-block masking of migration errors. LLD §5 language updated. |
| M0.T2.2 Migration 001 (extensions + enums) | ✅ | `pgcrypto`, `citext`; enums: `org_role`, `project_role`, `methodology`, `portal_mode`, `invitation_state` |
| M0.T2.3 Migration 002 (identity + tenancy) | ✅ | `organizations`, `users`, `invitations`, `clients`, `projects`, `project_members` with FKs, CHECK constraints, and partial index for `invitations.state = 'pending'` |
| M0.T2.4 Singleton bootstrap seed | ⚠️ | `ensure_singleton_organization`, `has_org_admin`, `is_bootstrapped` service functions delivered. The `/setup` route + first-run redirect is roadmap-owned by M0.T7 |
| M0.T2.5 Models + SAVEPOINT-per-test fixture | ✅ | 7 model classes + `TenantScopedMixin`; `db_session` fixture uses `join_transaction_mode="create_savepoint"` for test isolation |

### M0.T3 — Auth + RBAC

| Subtask | Status | Notes |
|---|---|---|
| M0.T3.1 Argon2id hashing | ✅ | Settings-driven cost params (default 64 MiB / 3 iter / 1 parallel per NFR-5.2.1) |
| M0.T3.2 JWT access + rotating refresh | ✅ | Access = HS256 JWT (sub+type+iat+exp+jti). Refresh = opaque token, SHA-256 hash stored in `refresh_tokens`. Rotation writes `revoked_at='rotated'` on the old row and `rotated_from` on the new row |
| M0.T3.3 OIDC pathway (feature-flagged) | ⚠️ | `oidc_enabled` + `oidc_issuer`/`client_id`/`client_secret`/`scopes` settings + `get_oidc_config()` factory delivered. Actual Authlib redirect/callback flow is NOT wired — matches roadmap intent ("opt-in in v1") |
| M0.T3.4 Invitation issue + accept | ✅ | Raw token returned exactly once from `POST /invitations`; `POST /invitations/accept` creates the user + optional `ProjectMember` + issues tokens |
| M0.T3.5 RBAC dependency factories | ✅ | `get_current_user`, `require_org_role(...)`, `require_project_membership(...)`, `require_agent_permission(agent_role)` — the agent matrix skeleton is in place for M1.T3 to consume |
| M0.T3.6 404-not-403 policy | ✅ | Enforced inside `require_project_membership` — missing membership OR missing project → 404. Wrong role inside a visible project → 403 (deliberate distinction) |
| M0.T3.7 CSRF double-submit cookie middleware | ✅ | Three exemption layers: (1) no cookie yet → set + skip, (2) Bearer auth → skip, (3) auth entry paths (login/refresh/invitations/accept) whose body-scoped secret is the boundary → skip |
| ➕ Migration 004 `audit_log` | ➕ | Not on the T3 subtask list, but needed to satisfy CLAUDE.md §1.5 (audit inside same transaction) for auth events. Table + `AuditSink.write` service delivered |
| ➕ Error taxonomy | ➕ | `InvalidCredentials` (401), `InvalidToken` (401), `InvitationInvalid` (410) added to `app/api/errors.py` |

---

## 3. Deferrals — sanctioned by the roadmap or explicitly scoped out

These are NOT bugs. They were either explicitly deferred by the roadmap or fall in a later milestone.

- **OIDC IdP integration flow** — surface + config only in M0.T3. Actual redirect/callback wire-up unscheduled; SRS §FR-4.1.2 says "where the operator configures an IdP" which implies opt-in configuration, not v1 core functionality.
- **First-run `/setup` UI + route** — `services/bootstrap.py` is ready. The redirect and screen land in **M0.T7**.
- **Frontend auth UI** — placeholder home page only. Login, dashboard, board come in **M0.T6**.
- **Password reset flow** — SRS §FR-4.1.7 lists it; not on M0.T3 subtasks. Will land alongside or after M0.T7.
- **Email delivery (SMTP)** — invitations exist in DB with a raw token surfaced once via API response. Actual SMTP send is optional per SI-5; deferred.
- **Full LICENSE text** — repo carries the AGPL-3.0 SPDX header + FSF URL. Full text must be pasted before public release per **M4.T3.3**.
- **OpenAPI diff CI check** — placeholder job. Activates in **M1.T3** when the artifact endpoints ship a stable OpenAPI spec worth pinning.
- **Traceability check enforcement** — extraction commands work; warnings only during pre-alpha. Will block on missing anchors starting when milestones are marked done.
- **Login-specific rate limiting** — global rate limit lands in **M3.T6**; per-endpoint throttling not yet.
- **Refresh-token pruning job** — expired refresh_tokens rows accumulate. Add to **M0.T7** or **M3.T6**. Not urgent at v1 scale.
- **Integration-test job in CI** — integration tests run locally via testcontainers. CI job needs docker-in-docker configuration; deferred.
- **Real API client codegen** — `packages/api-client/` is a placeholder; codegen wires up in **M1.T3**.

---

## 4. Caveats — delivered but with a known limitation

These work today but have a known trade-off or non-ideal shape. Track them if they start to bite.

### 4.1 Session-scoped test loop is off — engine + db_session are function-scoped

`pytest-asyncio` on Windows crashes when session-scoped async fixtures hold connections that get cleaned up in per-test loops (asyncpg + ProactorEventLoop). Fixture creates a fresh async engine per test (~5ms overhead, tolerable). Testcontainer + Alembic migrations remain session-scoped. See [feedback-pytest-asyncio-loop-scope](../../../../../Users/eepl/.claude/projects/d--UnderDev-SelfDev-Krititva-AI/memory/feedback_pytest_asyncio_loop_scope.md).

### 4.2 `.example.com` in test emails

Pydantic's `EmailStr` (via `email-validator`) rejects `.test`, `.local`, `.localhost`, `.invalid` TLDs from IANA's special-use list. Test factories use `@example.com`. Not a bug; a testing convention worth remembering. See [feedback-test-email-domains](../../../../../Users/eepl/.claude/projects/d--UnderDev-SelfDev-Krititva-AI/memory/feedback_test_email_domains.md).

### 4.3 `postgresql.ENUM` in Alembic `op.create_table`

`sa.Enum(..., create_type=False, native_enum=True)` inside an `op.create_table` still emits a duplicate `CREATE TYPE` on some SQLAlchemy versions. Migration 002 uses `postgresql.ENUM(..., create_type=False)` via a `_enum()` helper. Any future migration referencing a previously-created enum MUST follow the same pattern. See [feedback-pg-enum-in-migrations](../../../../../Users/eepl/.claude/projects/d--UnderDev-SelfDev-Krititva-AI/memory/feedback_pg_enum_in_migrations.md).

### 4.4 Advisory lock switched to `pg_advisory_xact_lock`

The original LLD §5 concept was a session-scoped `pg_advisory_lock` released in a `finally` block. That pattern (a) masked real migration errors when the transaction was already aborted, and (b) failed under asyncpg's post-error state. Current implementation uses `pg_advisory_xact_lock` inside `context.begin_transaction()` — auto-released on COMMIT or ROLLBACK. Serialization guarantee is unchanged; error surfacing is now clean.

### 4.5 CSRF exemption for auth entry paths

`login`, `refresh`, `invitations/accept` bypass CSRF (path-suffix match in `CSRF_EXEMPT_SUFFIXES`). Rationale: those endpoints authenticate via body-carried secrets (email+password, refresh token, one-time invitation token), which are already the security boundary. This is the standard shape but is worth flagging so nobody adds a state-changing endpoint under `/auth/` without thinking.

### 4.6 Refresh token concurrent-use race window

`AuthService.refresh` does `SELECT ... WHERE revoked_at IS NULL` → mark old revoked → INSERT new. No `SELECT ... FOR UPDATE`. Two concurrent refresh calls could theoretically both succeed (each issues a new token, and the old row gets `revoked_reason='rotated'` written twice — idempotent). Cost: two valid refresh tokens instead of one for a short window. If this becomes a security concern, add `SELECT ... FOR UPDATE SKIP LOCKED` on the SELECT.

### 4.7 IDE "package not installed" hints

VSCode's Python extension throws false-positive hints on `pyproject.toml` dependency lines. Packages ARE installed (uv sync worked, pytest passes). The fix is workspace-side: point VSCode at `apps/api/.venv/Scripts/python.exe`. Not a code issue.

### 4.8 `testcontainers` deprecation warnings

`@wait_container_is_ready` decorator is deprecated in testcontainers-python 4.x. Still functional. Silence when testcontainers ships the replacement structured wait strategies as the default.

### 4.9 Fixed 8-char password minimum on invitation accept

`InvitationAcceptRequest.password: Field(min_length=8)` hardcoded. Real policy should read from settings and reject common passwords. Land alongside password reset.

---

## 5. Non-caveats — known-good architectural choices

Worth calling out so they're not re-litigated:

- **JWT access tokens are minimal** (sub + type + iat + exp + jti). User email / org_role / memberships are NOT in the claims — those are resolved via DB lookup in `get_current_user`. Cost: one indexed PK lookup per request. Benefit: no JWT staleness bugs when email/role changes.
- **Refresh tokens are opaque, not JWTs**. Stored as SHA-256 hash. Enables server-side revocation on demand and preserves the audit trail via `rotated_from`.
- **Argon2id parameters are configurable via `KRITITVA_ARGON2_*` env vars** — the operator can tune for the target hardware without a rebuild.
- **Routes own authorization; services own persistence**. Auth checks happen at the FastAPI dependency layer (`require_*`); services (`AuthService`, `AuditSink`) just execute. Simplifies both testing and reasoning about who can do what.
- **Audit is written in the same transaction as the business change** — `AuditSink.write` flushes; the caller commits. Never a two-phase audit path.
- **Multi-tenancy is a nullable-column posture**. `organization_id` is populated on every INSERT even though nullable at the DB level. Future non-null migration is a backfill, not a schema rewrite.

---

## 6. Files added / touched (representative, not exhaustive)

### apps/api/app/
- `config.py` — settings incl. JWT secret, Argon2id params, CSRF cookie/header names, OIDC surface, invitation TTL
- `db.py` — async engine + `session_scope`
- `api/deps.py` — `get_db`, `get_current_user`, three RBAC factories
- `api/errors.py` — DomainError hierarchy + FastAPI exception handler registration
- `api/routes/health.py` — `/livez` + `/readyz`
- `api/routes/auth.py` — 6 `/auth/*` endpoints
- `models/*` — 7 model modules + `enums.py` + `base.py`
- `migrations/env.py` — with `pg_advisory_xact_lock` + `Base.metadata` binding
- `migrations/versions/{0001,0002,0003,0004}_*.py` — the four migrations
- `security/{hashing,jwt,csrf,oidc}.py` — the four security primitive modules
- `services/{audit,auth,bootstrap}.py` — three services

### apps/api/tests/
- `conftest.py` — root fixtures
- `test_health.py`
- `security/{test_hashing,test_jwt}.py`
- `integration/conftest.py` — testcontainer, engine, db_session, client
- `integration/_factories.py` — user/org/project/member helpers
- `integration/{test_migrations,test_bootstrap,test_models_roundtrip,test_auth_login,test_auth_refresh,test_auth_logout_me,test_auth_invitations,test_rbac,test_csrf}.py`

### apps/web/
- `package.json`, `next.config.ts`, `tsconfig.json`, `tailwind.config.ts`, `components.json`
- `app/{layout,page}.tsx`, `app/globals.css`
- `lib/utils.ts`

### Root
- `package.json`, `pnpm-workspace.yaml`, `turbo.json`, `.gitignore`, `.editorconfig`, `.nvmrc`, `.python-version`, `LICENSE`, `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `.env.example`

### deploy/
- `docker-compose.yml`, `litellm.config.yaml`, `nginx.conf`

### packages/
- `methodology-templates/{agile,waterfall,hybrid}.json` + `schema.json`
- `api-client/` placeholder

### .github/
- `workflows/{ci,license-audit,dco}.yml`, `dependabot.yml`, `PULL_REQUEST_TEMPLATE.md`

### .claude/
- `CLAUDE.md`, `settings.json`
- `skills/{krititva-scaffold-module,krititva-migration,krititva-role-profile,krititva-verify-traceability}/SKILL.md`

---

## 7. What's next

**M0.T4 — Projects, clients, methodology config.** Depends on M0.T2 (schema) and M0.T3 (auth). The methodology JSON already exists in `packages/methodology-templates/`; this task wires them into project creation and adds the config-edit endpoints.

Immediate follow-ups from this report that should be tracked:
1. Add refresh-token pruning cron (M0.T7 or M3.T6).
2. Land password reset + `SessionRevokeOnPasswordChange` (post M0.T7).
3. Wire the integration-test CI job (docker-in-docker or a hosted Postgres runner).
4. Enable the traceability check as blocking once milestones start closing.
5. Paste the full AGPL-3.0 text into `LICENSE` before **M4.T3**.

---

## 8. Change log against docs

Adjustments to the specs made during M0.T1–T3, all applied in this update:

- **LLD §2.2** — added `refresh_tokens` table DDL (was implied by HLD §7.1 but not present in the LLD DDL).
- **LLD §2.3** — added a migration ordering note about `postgresql.ENUM` in `op.create_table`.
- **Roadmap** — M0.T1, M0.T2, M0.T3 subtasks marked ✅ with completion date.
- **Memory** — three feedback memories added during this work: `feedback_pg_enum_in_migrations`, `feedback_test_email_domains`, `feedback_pytest_asyncio_loop_scope`. Now referenced from this completion doc so future sessions can find them via the doc index.

No SRS changes were required — everything M0.T1–T3 satisfies existing SRS requirements.

---

## 9. M0.T4 — Projects, clients, methodology config

**Status:** Delivered 2026-07-07. Test count **78 / 78** (was 52): +16 project integration tests, +10 methodology-loader unit tests. `mypy --strict` clean on 43 source files (was 35).

### 9.1 Subtask delivery

Legend: ✅ delivered · ⚠️ caveat · ➕ beyond scope

| Subtask | Status | Notes |
|---|---|---|
| M0.T4.1 Migration 005 | ✅ | `work_item_kind` enum + `workflow_states`, `workflow_transitions` (`approval_quorum JSONB`), `hierarchy_rules`. Numbered **005**, not 003 — 003/004 were consumed by refresh_tokens/audit_log. Round-trip (downgrade→upgrade) verified. |
| M0.T4.2 Wire templates | ✅ | `app/methodology/` loads + validates `packages/methodology-templates/{agile,waterfall,hybrid}.json` into Pydantic models. Referential integrity enforced at load: transitions reference real state keys; hard gates carry a non-empty `approval_quorum`; unknown roles rejected. |
| M0.T4.3 `POST /projects` atomic | ✅ | Project row + all states/transitions/hierarchy seeded in one transaction; creator enrolled as `project_owner`. `DuplicateKey` (409) pre-check on `key`. Route commits once; template failure rolls the whole thing back. |
| M0.T4.4 Config-edit + in-use safety | ✅ | `PATCH /workflow/transitions/{tid}`, `PATCH /hierarchy-rules` (replace-all), `PATCH /methodology`. In-use inspectors (`_work_item_kinds_in_use`, `_parent_child_pairs_in_use`) are the seam for M0.T5 — they return empty today, and `ConfigInUse` (409) fires on removed-but-used. |
| M0.T4.5 Frontend settings page | ⚠️ | `app/projects/[projectId]/settings` renders states/transitions/hierarchy + a read-only LLM-config card. Data source is a typed placeholder (`lib/methodology.ts`) pending auth (M0.T6) and the generated api-client (M1.T3). |
| ➕ `GET /projects/{id}` + methodology reads | ➕ | `GET /projects/{id}`, `GET /workflow/{states,transitions}`, `GET /hierarchy-rules` — needed so the settings page (and M0.T5) can read config. |
| ➕ Error taxonomy | ➕ | `DuplicateKey` (409), `ConfigInUse` (409), `InvalidWorkflowConfig` (422) added to `app/api/errors.py`. |

### 9.2 Endpoints live (added this task)

```
POST   /api/v1/projects
GET    /api/v1/projects/{id}
PATCH  /api/v1/projects/{id}/methodology
GET    /api/v1/projects/{id}/workflow/states
GET    /api/v1/projects/{id}/workflow/transitions
PATCH  /api/v1/projects/{id}/workflow/transitions/{tid}
GET    /api/v1/projects/{id}/hierarchy-rules
PATCH  /api/v1/projects/{id}/hierarchy-rules
```

### 9.3 Deferrals (roadmap-sanctioned or later-milestone)

- **`PUT /projects/{id}/llm-config`** — LLD §4.2 lists it; the `LLMConfig` schema is delivered (`app/schemas/llm_config.py`) but the mutating endpoint is deferred with the settings UI edit flow. Frontend shows it read-only.
- **`POST/DELETE /projects/{id}/members`** — LLD §4.2. Membership is currently created via the invitation-accept flow (M0.T3) and the auto-enroll of the creator. Direct member management is not on the M0.T4 subtask list.
- **In-use enforcement with real data** — the safety-check pattern is in place but exercises no rows until `work_items` lands (M0.T5). When it does, fill `_work_item_kinds_in_use` / `_parent_child_pairs_in_use` with real queries — the call sites already gate on them.
- **State add/remove & transition add/remove endpoints** — LLD §4.3 surfaces only `GET` states and `PATCH` transition / hierarchy replace-all. Structural add/remove of states is not in v1's API surface.

### 9.4 Caveats

- **`disabled_agents: list[str]`** in `LLMConfig` — LLD §11 types it `list[agent_role]`, but the `agent_role` enum arrives with the agent matrix in M1.T3. Tightens then.
- **`POST /projects` is gated on `org_admin`** (not the LLD's `[org_admin | project_owner-role]`). A brand-new project has no owner yet, so `project_owner` can't be a creation gate; the creator is auto-enrolled as `project_owner` post-create.
- **`reseed_workflow=true`** on methodology change wipes + re-applies the template's workflow config. Guarded by the in-use inspector (no-op today). Default is `false` → methodology label changes, workflow rows untouched (FR-4.2.3: no retroactive rewrite).

### 9.5 Change log against docs

- **Roadmap** — M0.T4 + its five subtasks marked ✅ with the migration-005 correction noted.
- **LLD** — no DDL change needed; migration 005 matches §2.2 exactly (the three tables are project-scoped and intentionally carry no `organization_id`).
- **New source** — `app/methodology/` (template loader), `app/schemas/{project,methodology,llm_config}.py`, `app/services/project.py`, `app/api/routes/projects.py`; frontend `app/projects/[projectId]/settings/`, `components/ui/{card,badge}.tsx`, `lib/methodology.ts`.
- **Config** — added `KRITITVA_METHODOLOGY_TEMPLATES_DIR` (default: repo `packages/methodology-templates/`).

No SRS changes were required — everything M0.T4 satisfies existing FR-4.2.* / FR-4.3.* requirements.

---

## 10. M0.T5 — Work Item Engine core

**Status:** Delivered 2026-07-07. Test count **131 / 131** (was 78): +18 work-item HTTP integration, +28 direct-service engine, +7 lexorank property/unit. `mypy --strict` clean on 50 source files.

### 10.1 Subtask delivery

Legend: ✅ delivered · ⚠️ caveat · ➕ beyond scope

| Subtask | Status | Notes |
|---|---|---|
| M0.T5.1 Migration 006 | ✅ | `work_items`, `work_item_links`, `sprints`, `milestones`, `stale_flags` + enums `link_type` / `gate_status` / `stale_reason`. Numbered **006** (004 was audit_log). |
| M0.T5.2 `create` | ✅ | Hierarchy-rule check (422 + offending pair, FR-4.4.3), per-project `seq` (FR-4.4.2), human key `<project.key>-<seq>`, initial-state pick (first todo-category by sort_order), append rank. |
| M0.T5.3 `transition` | ✅ | Edge lookup (422 if none), required-role with project_owner override (403 otherwise), hard gate → 409 `gate_not_approved`. |
| M0.T5.4 `link` | ✅ | Cycle-safe on `derived_from` (self + transitive) via an app-level reachability walk → 422 `link_cycle_detected`. `tests`/`blocks`/`relates_to` are not cycle-checked. |
| M0.T5.5 `rerank` | ✅ | Fractional indexing (base-62, jitter-free). Single-row writes — no periodic full rebalance needed (FR-4.4.7). Property-tested with Hypothesis. |
| M0.T5.6 `bulk_transition` | ✅ | Per-item auth + per-item error via nested savepoints; a failing item never rolls back the others (LLD: "never partially transactional across items"). |
| M0.T5.7 lineage | ⚠️ | `GET /work_items/{id}/lineage` walks `derived_from` work-item edges (depth-bounded, cycle-safe). The SQL `lineage_chunks` function is **deferred to M1** — see §10.4. |
| M0.T5.8 branch coverage | ✅ | State-machine + hierarchy methods 100% branch (direct-service tests); service overall 98% (two defensive guards `# pragma: no cover`). |

### 10.2 Endpoints live (added this task)

```
POST   /api/v1/projects/{id}/work_items
GET    /api/v1/projects/{id}/work_items
GET    /api/v1/projects/{id}/work_items/{wid}
PATCH  /api/v1/projects/{id}/work_items/{wid}
POST   /api/v1/projects/{id}/work_items/{wid}/transitions
POST   /api/v1/projects/{id}/work_items/{wid}/links
POST   /api/v1/projects/{id}/work_items/{wid}/rerank
POST   /api/v1/projects/{id}/work_items/bulk-transition
GET    /api/v1/projects/{id}/work_items/{wid}/lineage
```

### 10.3 LLD deltas (applied)

- **`idx_wi_assignee_open`** — LLD §2.2 specifies `WHERE state_id IN (SELECT ...)`; Postgres forbids subqueries in index predicates. Shipped a plain `idx_wi_assignee` on `assignee_id`. The partial-index optimization can return later as an application-maintained boolean column if profiling wants it.
- **Deferred cross-module FKs** — `work_items.source_job_id` (→ ai_generation_jobs), `work_item_links.to_chunk` (→ document_chunks), `stale_flags.triggered_by` (→ document_versions) are plain UUID columns; the FK constraints are added by the M1 migration that creates their targets (LLD §2.3 cycle-deferral pattern).

### 10.4 Deferrals

- **`lineage_chunks` SQL function** — LLD §2.2 defines it, but its body JOINs `document_chunks`, which doesn't exist until M1; Postgres validates SQL-function bodies at creation, so it can't be created now. The lineage endpoint currently returns the work-item `derived_from` ancestry; chunk lineage activates when the function lands in M1.
- **Hard-gate crossing** — a hard gate is *blocked* now (409). The approval-quorum grant path (`milestone_approvals`, multi-sig) is M2. `milestones` ships as the base table; `milestone_approvals` is not yet created.
- **`sprints` / `milestones` write APIs** — tables exist (LLD §4.5/§4.6 endpoints) but the sprint/milestone CRUD services are M2/M3. Work items can reference a `sprint_id` / `milestone_id` once those exist.

### 10.5 Caveats

- **Coverage under ASGI** — coverage.py does not trace coroutines executed through the `httpx` ASGI transport, so HTTP-driven integration tests report the service as under-covered. The engine's real branch coverage is measured by the direct-service suite (`test_work_item_engine.py`). Worth remembering before trusting a coverage delta on any route-driven test.
- **`seq` generation is `MAX(seq)+1`** — no `SELECT ... FOR UPDATE`. Concurrent creates in one project could collide on `uq_work_items_project_seq` (one gets a 500, retryable). Fine at v1 scale; tighten with an advisory lock or a per-project counter if it bites.
- **`disabled_agents` / gate quorum** — unchanged from M0.T4; still awaiting the agent-role enum and multi-sig approvals (M1.T3 / M2).

No SRS changes were required — everything M0.T5 satisfies existing FR-4.4.* requirements.

---

## 11. M0.T6 — Frontend shell

**Status:** Delivered 2026-07-07. `apps/web` now builds a full authenticated shell. Gates: `pnpm typecheck`, `pnpm lint`, and `pnpm build` (production, with `typedRoutes`) all clean. Backend test count **132 / 132** (+1 for the new `GET /projects` list test).

### 11.1 Subtask delivery

Legend: ✅ delivered · ⚠️ caveat · ➕ beyond scope

| Subtask | Status | Notes |
|---|---|---|
| M0.T6.1 Route scaffolding | ✅ | `/`, `/login`, and an `(app)` route group: `dashboard`, `projects`, `projects/[projectId]/{,board,backlog,settings}`. Root redirects by session. |
| M0.T6.2 Auth flow | ✅ | BFF pattern — see §11.2. HTTP-only cookies, refresh-on-401, `middleware.ts` route gate, TanStack Query for client data. |
| M0.T6.3 Dashboard + list | ✅ | Server components over `GET /projects` (added this task). Widget grid + recent/all project cards. |
| M0.T6.4 Kanban board | ✅ | dnd-kit; a drop validates against `workflow_transitions`, fires an optimistic `POST /transitions`, and rolls back + toasts on a 4xx. |
| M0.T6.5 Backlog | ✅ | dnd-kit sortable ordered by lexorank; drag computes before/after neighbours and calls `POST /rerank` optimistically. |
| M0.T6.6 WorkItemDialog | ✅ | Parent picker filtered to kinds `hierarchy_rules` allows for the chosen child kind. |
| ➕ `GET /projects` | ➕ | Backend list endpoint (org_admin → all org projects; else memberships). LLD §4.2 gains it. |
| ➕ Settings relocated | ➕ | The M0.T4 placeholder `app/projects/[projectId]/settings` moved into `(app)` and rewired to live data (`serverApi`), replacing the mock `lib/methodology.ts`. |

### 11.2 Auth architecture (BFF)

The backend authenticates via `Authorization: Bearer`. A browser can't attach a Bearer header from an HTTP-only cookie, and a plain Next rewrite can't inject one — so all backend traffic goes through Next route handlers that hold the credential:

- `app/api/auth/login` → calls backend `/auth/login`, sets `krititva_access` + `krititva_refresh` HTTP-only cookies.
- `app/api/v1/[...path]` → catch-all proxy: reads the access cookie, forwards to the backend with a Bearer header; on 401 it transparently refreshes (updating cookies) and retries once. Client TanStack Query hooks call this same-origin proxy.
- `lib/api/server.ts` (`serverApi`) → Server Components read the cookie via `next/headers` and call the backend directly with Bearer.
- `middleware.ts` → redirects to `/login` when neither session cookie is present (UX gate; the backend remains the real authority). Bearer auth also bypasses backend CSRF, so no CSRF-token juggling.

### 11.3 New frontend surface

```
app/
  page.tsx                          session-aware redirect
  login/page.tsx                    login (BFF)
  providers.tsx                     TanStack Query + Toaster
  api/auth/{login,logout}/route.ts  cookie-setting BFF
  api/v1/[...path]/route.ts         bearer-injecting proxy (refresh-on-401)
  (app)/layout.tsx                  sidebar + topbar (loads /auth/me)
  (app)/dashboard, projects, projects/[projectId]/{,board,backlog,settings}
components/ui/                       button, input, label, dialog, select, skeleton (+ card, badge)
components/                         app-sidebar, project-nav, login-form, logout-button,
                                    toaster, work-item-dialog, board/*, backlog/*
lib/api/{types,config,server,client}.ts · lib/hooks/work-items.ts · lib/toast.ts
middleware.ts
```

New runtime deps (all in the declared stack, AGPL-compatible MIT): `@dnd-kit/{core,sortable,utilities}`, `@radix-ui/react-{dialog,label,select}`.

### 11.4 Deferrals / caveats

- **Not runnable end-to-end here** — this environment has no live API + seeded DB, so the shell is verified by `typecheck` + `lint` + production `build` (which typechecks routes and RSC boundaries), not by Playwright. E2E against docker-compose is `main`-only per CLAUDE.md §5.
- **`/setup` first-run screen** — M0.T7. Login assumes a user already exists (created via the bootstrap seed / invitation flow).
- **`[projectId]` not `[key]` in URLs** — deviates from the LLD §7.1 route map's cosmetic `[key]`; there's no key→id endpoint and every API route is id-addressed. Revisit if a `GET /projects?key=` lands.
- **Toasts** are a minimal in-house Zustand store (no `sonner` dep) — enough for the "roll back + toast the error code" contract; swap for a richer system later if needed.
- **No document/AI/roadmap/portal routes** — out of M0 scope (documents M1+, AI panel M1.T3, roadmap M3, portal M3).

No SRS changes were required — M0.T6 satisfies UI-1 and UI-4.

---

## 12. M0.T7 — Bootstrap + operator experience

**Status:** Delivered 2026-07-07 — **closes M0 Foundation.** Backend **142 / 142** (+10: 4 setup-flow integration, 6 CLI unit). Frontend `typecheck` + `lint` + `build` clean (adds the `/setup` route).

### 12.1 Subtask delivery

| Subtask | Status | Notes |
|---|---|---|
| M0.T7.1 First-run `/setup` | ✅ | `bootstrap_setup` service + `POST /auth/setup` (public, one-time — 409 `already_bootstrapped` once an admin exists) creates the singleton org + first `org_admin` and logs in. `GET /auth/bootstrap` → `{bootstrapped}`. Frontend `/setup` page + `SetupForm` + BFF route; root and login pages redirect un-bootstrapped installs to `/setup`, and `/setup` bounces to `/login` once done. |
| M0.T7.2 Health probes | ✅ | `/livez` (process) + `/readyz` (DB round-trip) — shipped in M0.T2/T3; confirmed, unchanged. |
| M0.T7.3 `krititva` CLI | ✅ | `app/cli.py` + `krititva` console script. `backup` (pg_dump `-Fc` + `shutil.copytree` of assets), `restore` (pg_restore `--clean --if-exists`), `--print-only` to emit commands. Command builders are pure + unit-tested; DSN is converted from the async driver to libpq form. |
| M0.T7.4 Quickstart docs | ✅ | `README.md` five-step self-host quickstart matching the M0 exit checklist. |

### 12.2 Security note — the one-time setup door

`POST /auth/setup` is public (no session exists yet) and CSRF-exempt (body-carried secrets are the boundary, like login). Its safety rests entirely on the `has_org_admin` guard: the instant one active `org_admin` exists it returns 409, so it can never be used to mint a second admin. Tested directly (`test_setup_is_one_time`).

### 12.3 New / changed surface

- Backend: `services/bootstrap.py` (`bootstrap_setup`), `routes/auth.py` (`GET /auth/bootstrap`, `POST /auth/setup`), `schemas/auth.py` (`BootstrapStatus`, `SetupRequest`), `errors.py` (`AlreadyBootstrapped`), `security/csrf.py` (`/auth/setup` exempt), `cli.py`, `pyproject.toml` (`krititva` script + `app/cli.py` ruff per-file ignore for print/subprocess).
- Frontend: `app/setup/page.tsx`, `components/setup-form.tsx`, `app/api/auth/setup/route.ts`, `lib/api/bootstrap.ts`; redirect wiring in `app/page.tsx` + `app/login/page.tsx`.

### 12.4 Deferrals / caveats

- **"Pull recommended local models" one-click** (FR-4.12.2) — not built; the operator pulls Ollama models manually per the README. It's an optional, network-permitting convenience, deferrable past M0.
- **CLI runs unverified against a real Postgres here** — `backup`/`restore` construct and (non-`--print-only`) execute `pg_dump`/`pg_restore`, but the round-trip isn't exercised in CI (no pg client binaries in the unit env). Command construction is unit-tested; the live round-trip belongs in the tagged-release smoke suite.
- **No auto-bootstrap on startup** — intentional (FR-4.12.2 wording); the operator completes `/setup`. Migrations *do* auto-run at api start under the advisory lock (FR-4.12.4), unchanged from M0.T2.

### 12.5 M0 Foundation — done

The end-to-end M0 slice stands: Postgres schema (6 migrations, 16 tables), Argon2id auth + JWT/refresh + RBAC (404-not-403), methodology-as-data project creation, the work-item engine (hierarchy, state machine, cycle-safe links, lexorank), the Next.js BFF shell (dashboard, board, backlog, settings), and first-run + operator tooling. Aggregate: **142 backend tests**, `mypy --strict` clean on 52 source files, frontend `build` clean. Live docker-compose smoke + Playwright E2E are the `main`-branch gates per CLAUDE.md §5.

No SRS changes were required — M0.T7 satisfies FR-4.12.1–4.12.5 (4.12.2's optional model-pull deferred).

---

## 13. Post-M0 — peer review + first Docker bring-up (2026-07-13)

After M0 was committed, two hardening passes ran before starting M1.

### 13.1 End-to-end peer review — 13 bugs, all fixed

Three parallel reviewers (auth/security, engine/data, frontend) + per-finding verification (the collation bug was confirmed against a live Postgres). All genuine; fixed priority-first. Test count **142 → 148** (+6 regression tests). Committed.

- **HIGH #1 — lexorank collation:** `work_items.rank` was plain `TEXT`, inheriting the DB's `en_US.utf8` collation where `'a' < 'Z'` — the inverse of the algorithm's bytewise assumption. `ORDER BY`/`MAX(rank)` mis-sorted and `_append_rank` minted duplicate keys. Fix: migration **0007** → `rank TEXT COLLATE "C"` + model `Text(collation="C")` + a regression test that drives the a/Z boundary through the DB. Only reproducible via Postgres, never in the pure-Python property tests. See [feedback-lexorank-collation].
- **HIGH #2 — server 401 handling:** RSC `serverApi` threw on 401; only `(app)/layout` caught it, so a client sub-navigation after token expiry hit Next's error page instead of re-auth. Fix: `serverApiAuthed` redirects 401/403 → `/login`, used across `(app)` pages.
- **MED #3 — in-use safety inert:** `ProjectService._work_item_kinds_in_use` / `_parent_child_pairs_in_use` still returned `set()` after M0.T5 shipped, so FR-4.3.2 was silently unenforced (and reseed 500'd on the state FK). Fix: wired to real queries → 409 `config_in_use`.
- **MED #4–6:** first-run `/setup` TOCTOU (added `pg_advisory_xact_lock`); open-redirect via `next=//host` (guarded); accepting an invite for an already-registered email → typed 409 (was an unhandled 500).
- **LOW #7–13:** cross-project/non-member `assignee_id`/`sprint_id`/`milestone_id` validated (422 `invalid_reference`); login dummy-hash (timing oracle); prod fail-fast on default/empty `jwt_secret`; `/readyz` → 503 on DB down; BFF proxy header safelist; CSRF exact-path match; client 401 → `/login`.

### 13.2 First Docker bring-up — ~10 deploy bugs, all fixed

`deploy/docker-compose.yml` had never been run. Bringing it up (and the sign-up flow through the browser) surfaced real bugs, all fixed — see [feedback-docker-deploy] for the durable list. Headlines: web Dockerfile `adduser` uid collision; **missing root `.dockerignore`** (host `node_modules` clobbered the image's); `output: "standalone"` never enabled (gated behind `BUILD_STANDALONE=1`); api `uv sync` installed into `./.venv` not the shipped `/venv` (fixed with `UV_PROJECT_ENVIRONMENT=/venv` + copy `uv.lock`); `templates.py` `parents[4]` broke in the flattened container (now walks up for `packages/methodology-templates`, which is copied into the image); migrations wired into the api `command`; the worker crash-looped with zero arq functions (added a `ping` no-op); and the sign-up `ECONNREFUSED` — the web BFF read `KRITITVA_API_URL` but compose set only `NEXT_PUBLIC_API_URL`.

**Verified:** `docker compose -f deploy/docker-compose.yml --env-file .env up -d --build` runs all 6 services; api auto-migrates at start; `POST http://localhost:3000/api/auth/setup` (through the web BFF) returns 200 and sets the HttpOnly cookies. Compose commands require `--env-file .env` (with `-f`, compose reads `.env` from the file's directory, not the repo root).

### 13.3 Uncommitted at handoff

The final deploy round is uncommitted (3 files): `apps/api/app/workers/arq_settings.py`, `apps/api/app/config.py`, `deploy/docker-compose.yml`. Commit before M1. *(Resolved: committed as `e08f02d` before M1.T1 started.)*

---

## 14. M1.T1 — Document service + versioning (2026-07-13)

**Status:** Backend delivered. Test count **167 / 167** (was 148): +11 direct-service (`test_documents_service.py`), +8 HTTP (`test_documents.py`). `mypy --strict` clean on 55 source files; ruff clean. Traces: FR-4.5.1–4.5.4, FR-4.5.7–4.5.9, FR-4.10.4 · LLD §2.2 (documents), §2.3 (ordering), §3.1 (DocumentService), §4.7.

### 14.1 Subtask delivery

Legend: ✅ delivered · ⚠️ caveat/deferred · ➕ beyond scope

| Subtask | Status | Notes |
|---|---|---|
| M1.T1.1 Migration **0008** | ✅ | `documents` + `document_versions`. Roadmap said "005" — 0001–0007 were used, so this is **0008**. Enums `doc_type` / `doc_status` created first. `documents ↔ document_versions` cycle resolved via `fk_current_version` added after both tables exist (LLD §2.3). Deferred FK `stale_flags.triggered_by → document_versions` now resolved. `document_versions` is append-only (no `updated_at`). `ai_job_id` stays a plain UUID until M1.T3 (`fk_dv_ai_job`). |
| M1.T1.2 `create_version` | ✅ | Optimistic lock: head = latest `version_no`. `base_version_id` must equal head id (or both `None` when no versions exist), else `VersionConflict` (409, `version_conflict`) with `head_version_id`/`head_version_no` detail. Append-only; content SHA-256 hashed; a draft never mutates `current_version_id`. |
| M1.T1.3 `approve` | ✅ | Single-approved invariant via partial unique index `idx_doc_one_approved` + supersede-prior (status → `superseded`, an allowed forward transition per §1.3). Sets `documents.current_version_id` to the approved version (the canonical pointer the retrieval join reads, LLD line 833). Only `draft`/`in_review` are approvable → else `InvalidDocumentState` (422). |
| M1.T1.4 PDF export | ⚠️ | **Deferred, pending your decision.** Needs a headless-render runtime dep (WeasyPrint / Playwright-chromium) whose license needs review per §1.7/§14. `GET .../export.pdf` path reserved, not wired. |
| M1.T1.5 Frontend DocumentEditor | ⚠️ | **Deferred, pending your decision.** TipTap + Mermaid.js are new frontend runtime deps needing AGPL-compat check per §1.7/§14. |

### 14.2 Endpoints live (added this task)

```
POST   /api/v1/projects/{id}/documents
GET    /api/v1/projects/{id}/documents
GET    /api/v1/projects/{id}/documents/{did}
POST   /api/v1/projects/{id}/documents/{did}/versions
GET    /api/v1/projects/{id}/documents/{did}/versions
GET    /api/v1/projects/{id}/documents/{did}/versions/{vid}
POST   /api/v1/projects/{id}/documents/{did}/versions/{vid}/approve
```

### 14.3 Decisions / notes

- **`current_version_id` = the approved (canonical) version**, not the latest draft — confirmed against the retrieval join in LLD §? (`JOIN documents d ON d.current_version_id = v.id`) and the "prerequisite reads `status='approved'`" delta (LLD §10). `create` leaves it NULL; drafts don't touch it; `approve` sets it.
- **RBAC (LLD-unspecified, decided here):** authoring documents + drafting versions = contributor roles (owner/scrum_master/developer/qa); **approving = owner/scrum_master only** (canonical mutation, mirrors draft-and-review §1.1). Revisit if M2 quorum work reclassifies doc approval.
- **New typed error** `InvalidDocumentState` (422, `invalid_document_state`) for approving a non-`draft`/`in_review` version. Not in the LLD §3.2 table; internal taxonomy addition.
- **`approved_at`** stamped with app-clock `datetime.now(UTC)` (no server default on that column).

### 14.4 Deferrals

- **Chunk+embed enqueue on `create_version`** — the LLD contract says `create_version` "enqueues chunk+embed job". The chunker + embedding worker + `document_chunks` table are **M1.T2**; until then a draft version is simply persisted. `get_chunks_for_retrieval` (LLD §3.1) also lands with M1.T2.
- **`lineage_chunks` SQL function** — now unblockable (its `document_chunks` JOIN target arrives in M1.T2, not T1). Still deferred to M1.T4.1 per the handoff.
- **PDF export (T1.4) and DocumentEditor (T1.5)** — see §14.1; both blocked on new-dependency license review (§14 stop-and-ask).

---

## 15. M1.T2 — Chunking + embedding pipeline (2026-07-13)

**Status:** Delivered (T2.1–T2.4; T2.5 deferred to a perf suite). Test count **184 / 184** (was 167): +12 chunker unit/property (`tests/engine/test_chunking.py`), +5 pipeline/retrieval integration (`tests/integration/test_embedding_pipeline.py`). `mypy --strict` clean on 62 source files; ruff clean. Traces: FR-4.5.4–4.5.6, NFR-5.1.3, NFR-5.1.5 · LLD §2.2 (document_chunks), HLD §5.4.

### 15.1 Subtask delivery

| Subtask | Status | Notes |
|---|---|---|
| M1.T2.1 Migration **0009** | ✅ | `CREATE EXTENSION vector` (first use), `document_chunks` (discriminated embeddings, append-only — no `updated_at`), partial HNSW indexes `idx_chunks_embedding` / `idx_chunks_embedding_alt` (`m=16, ef_construction=64`, `WHERE embedding[_alt] IS NOT NULL`), deferred FK `fk_link_chunk` (`work_item_links.to_chunk`) resolved. |
| M1.T2.2 Chunker | ✅ | `app/ai/chunking.py::chunk_markdown` — H1–H4 split, `section_path` breadcrumb (stack pops on same-or-shallower heading), preamble → empty path, SHA-256 hash. Property-tested. |
| M1.T2.3 Embed worker | ✅ | `app/ai/pipeline.py::run_chunk_and_embed` (core) + `app/workers/embed.py::chunk_and_embed` (arq wrapper, own session per §4.1) + `app/ai/embeddings.py` (`EmbeddingClient` protocol, `LiteLLMEmbeddingClient`, `FakeEmbeddingClient`). Registered in `WorkerSettings.functions`. Idempotent (chunk-once, embed-missing). |
| M1.T2.4 Retrieval | ✅ | `app/ai/retrieval.py::semantic_search` — joins `documents.current_version_id` (approved-only), filters project + doc_types + embedding_model, ranks by `embedding.cosine_distance`. |
| M1.T2.5 Load test | ⚠️ | **Deferred** to a tagged perf suite (NFR gate, not PR-CI unit work). |

### 15.2 New dependencies (license-checked, §1.7)

- **`pgvector`** (Python SQLAlchemy binding) — pinned `>=0.5.0,<0.6`. License: **MIT**. Note: 0.3.x installs as a PEP 420 namespace package that pytest's sys.path handling breaks under this uv/Windows setup; 0.5.0 ships a regular package, so we pin ≥0.5.0. See [[feedback-uv-sync-all-extras]].
- No tiktoken: it downloads its BPE vocab from the network on first use, which would violate the no-phone-home default (§1.6). Token counting uses a deterministic offline estimator instead.

### 15.3 Decisions / notes

- **`embedding_model` nullable** — LLD §2.1 delta note (4) says NOT NULL, but the definitive DDL block in §2.2 lists it nullable, which the chunk-then-embed flow requires (rows inserted before the vector exists). Followed §2.2. `embedding` + `embedding_model` are written together by the worker.
- **Enqueue trigger** — `create_version` enqueues `chunk_and_embed` after commit via a best-effort app arq pool (`app/queue.py`, `get_arq_pool` dep). Under ASGI-transport tests the lifespan doesn't run, so the pool is absent and enqueue is skipped — no Redis needed in PR CI. If Redis is down in production the request still succeeds; the job is simply not queued.
- **Token counting** — offline word/punctuation estimator (`estimate_tokens`); tracks BPE closely enough for chunk-packing budgets without a phone-home.
- **`get_chunks_for_retrieval` (LLD §3.1)** — the concrete retrieval lives in `semantic_search`; the DocumentService wrapper + Context Assembler integration land with the role profiles (M1.T4+).

### 15.4 Deferrals

- **M1.T2.5 load test** — see §15.1.
- **Project-level embedding-model selection** — the pipeline uses `DEFAULT_EMBEDDING_MODEL` (`nomic-embed-text`) until `llm_config` is wired to projects; the retrieval filter already keys on `embedding_model` so per-project models drop in cleanly.
- **`lineage_chunks` SQL function** — now fully unblockable (`document_chunks` exists); still slated M1.T4.1.
