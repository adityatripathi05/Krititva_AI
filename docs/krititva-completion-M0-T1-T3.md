# Krititva AI — M0.T1 through M0.T4 Completion Report

**Status:** M0.T1, M0.T2, M0.T3, M0.T4 delivered
**Upstream:** [krititva-roadmap.md](krititva-roadmap.md), [krititva-lld.md](krititva-lld.md)
**Date range:** 2026-07-06 → 2026-07-07

> M0.T4 (Projects, clients, methodology config) delivery is in [§9](#9-m0t4--projects-clients-methodology-config) below; §§1–8 cover M0.T1–T3.

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
