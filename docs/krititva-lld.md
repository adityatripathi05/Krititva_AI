# Krititva AI — Low-Level Design (v1.0)

**Status:** Draft for review
**Upstream:** [krititva-srs.md](krititva-srs.md), [krititva-hld.md](krititva-hld.md), [krititva-ai-blueprint.md](krititva-ai-blueprint.md)
**Downstream:** [krititva-roadmap.md](krititva-roadmap.md), phase-level plans (`.planning/phases/`)

This document specifies concrete implementations: SQL DDL with the four architect-review deltas applied, service class contracts, API endpoint specs, Pydantic schemas, and the Context Assembler algorithm. Everything below is directly implementable.

---

## 1. Package Layout (definitive)

```
krititva/
├── apps/
│   ├── web/                              Next.js 15 app
│   │   ├── app/                          App router
│   │   ├── components/                   shadcn/ui primitives
│   │   ├── lib/api/                      Generated OpenAPI client
│   │   └── ...
│   └── api/
│       └── app/
│           ├── main.py                   FastAPI app factory
│           ├── config.py                 Settings (pydantic-settings)
│           ├── db.py                     Session, engine, session_scope
│           ├── api/
│           │   ├── deps.py               get_db, get_current_user, get_arq_pool, get_org
│           │   ├── errors.py             Exception -> HTTP mapping
│           │   └── routes/
│           │       ├── auth.py
│           │       ├── organizations.py
│           │       ├── clients.py
│           │       ├── projects.py
│           │       ├── members.py
│           │       ├── work_items.py
│           │       ├── sprints.py
│           │       ├── milestones.py
│           │       ├── documents.py
│           │       ├── artifacts.py      AI job endpoints + SSE
│           │       ├── reports.py
│           │       └── audit.py
│           ├── models/                   SQLAlchemy ORM
│           ├── schemas/                  Pydantic (API + LLM output)
│           ├── services/
│           │   ├── auth.py
│           │   ├── tenancy.py
│           │   ├── projects.py
│           │   ├── work_items.py         Engine: hierarchy, transitions, cycles
│           │   ├── documents.py          Versioning, chunking, optimistic lock
│           │   ├── approvals.py          Multi-sig quorum
│           │   ├── ai_orchestrator.py    Job lifecycle + SSE bridge
│           │   ├── reports.py
│           │   └── audit.py              Audit sink
│           ├── ai/
│           │   ├── profiles/             One module per role agent
│           │   │   ├── base.py           Profile protocol
│           │   │   ├── project_owner.py
│           │   │   ├── architect.py
│           │   │   ├── scrum_master.py
│           │   │   ├── developer.py
│           │   │   └── qa.py
│           │   ├── context.py            ContextAssembler
│           │   ├── llm_client.py         Thin LiteLLM wrapper
│           │   ├── graphs/               LangGraph workflows
│           │   │   ├── epic_decompose.py
│           │   │   └── srs_ingest.py
│           │   └── prompts/              Jinja templates (data, not code)
│           ├── workers/
│           │   ├── arq_settings.py
│           │   ├── generation.py         run_artifact_generation
│           │   ├── embeddings.py         embed_chunks
│           │   ├── srs_diff.py           srs_supersession_diff
│           │   └── heartbeat.py          Stuck-job sweeper
│           └── migrations/               Alembic
├── packages/
│   ├── methodology-templates/            JSON seed
│   │   ├── agile.json
│   │   ├── waterfall.json
│   │   └── hybrid.json
│   └── api-client/                       Generated from OpenAPI
├── deploy/
│   ├── docker-compose.yml
│   ├── litellm.config.yaml
│   └── nginx.conf                        Reference reverse-proxy
├── docs/
│   ├── krititva-ai-blueprint.md
│   ├── krititva-srs.md
│   ├── krititva-hld.md
│   ├── krititva-lld.md
│   └── krititva-roadmap.md
├── pyproject.toml                        uv managed
├── turbo.json
└── package.json                          pnpm workspace root
```

---

## 2. Database Schema (definitive DDL)

### 2.1 Delta from blueprint v0.2

The four architect-review answers change:
1. All tenant-scoped tables gain `organization_id UUID NULL`.
2. `document_chunks` gets `embedding_model TEXT NOT NULL`, `embedding_alt vector(1536) NULL`, `embedding_alt_model TEXT NULL`.
3. `milestones` loses `approved_by`/`approved_at`; new table `milestone_approvals` handles multi-sig with `workflow_transitions.approval_quorum JSONB`.
4. `projects` gains `client_portal_mode` enum.

Additional deltas surfaced during LLD:
- `organizations` table added (singleton in v1).
- `invitations` table added.
- `refresh_tokens` table added — rotation-on-use ledger for NFR-5.2.2. Opaque tokens hashed with SHA-256; rotation writes a new row with `rotated_from` pointing at the revoked predecessor.
- `stale_flags` table added (§5.5 HLD).
- `worker_heartbeats` table for stuck-job detection (§FR-4.6.8).
- Cycle-safe recursive lineage helper as an SQL function.

### 2.2 Full DDL

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

-- ================================================================
-- Enumerations
-- ================================================================
CREATE TYPE methodology         AS ENUM ('agile', 'waterfall', 'hybrid');
CREATE TYPE org_role            AS ENUM ('org_admin', 'member');
CREATE TYPE project_role        AS ENUM ('project_owner', 'scrum_master',
                                         'developer', 'qa', 'viewer',
                                         'client_approver');
CREATE TYPE work_item_kind      AS ENUM ('phase', 'epic', 'feature', 'story',
                                         'task', 'bug', 'deliverable', 'test_case');
CREATE TYPE doc_type            AS ENUM ('srs', 'hld', 'lld', 'test_plan', 'other');
CREATE TYPE doc_status          AS ENUM ('draft', 'in_review', 'approved', 'superseded');
CREATE TYPE gate_status         AS ENUM ('pending', 'in_review', 'approved', 'rejected');
CREATE TYPE approval_decision   AS ENUM ('approve', 'reject');
CREATE TYPE agent_role          AS ENUM ('project_owner', 'architect',
                                         'scrum_master', 'developer', 'qa');
CREATE TYPE artifact_type       AS ENUM ('srs', 'epic_breakdown', 'hld', 'lld',
                                         'sprint_plan', 'story_breakdown',
                                         'task_breakdown', 'api_contract',
                                         'test_plan', 'test_cases');
CREATE TYPE job_status          AS ENUM ('queued', 'running', 'awaiting_review',
                                         'accepted', 'rejected', 'failed');
CREATE TYPE capacity_kind       AS ENUM ('availability', 'vacation', 'allocation');
CREATE TYPE link_type           AS ENUM ('derived_from', 'tests', 'blocks', 'relates_to');
CREATE TYPE portal_mode         AS ENUM ('none', 'export_only', 'portal');
CREATE TYPE invitation_state    AS ENUM ('pending', 'accepted', 'revoked', 'expired');
CREATE TYPE stale_reason        AS ENUM ('chunk_removed', 'chunk_changed', 'chunk_added_upstream');

-- ================================================================
-- Tenancy & identity
-- ================================================================
CREATE TABLE organizations (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id),   -- NULL allowed for v1; enforced later
    email           CITEXT UNIQUE NOT NULL,
    display_name    TEXT NOT NULL,
    password_hash   TEXT,                                -- NULL when SSO-only
    org_role        org_role NOT NULL DEFAULT 'member',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    tz              TEXT NOT NULL DEFAULT 'UTC',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deactivated_at  TIMESTAMPTZ
);
CREATE INDEX idx_users_org ON users(organization_id);

CREATE TABLE invitations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id),
    email           CITEXT NOT NULL,
    invited_by      UUID NOT NULL REFERENCES users(id),
    project_id      UUID,                                -- optional pre-assigned project
    project_role    project_role,
    token_hash      TEXT NOT NULL,                       -- SHA-256 of one-time token
    state           invitation_state NOT NULL DEFAULT 'pending',
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    accepted_at     TIMESTAMPTZ,
    accepted_user   UUID REFERENCES users(id)
);
CREATE INDEX idx_invitations_email ON invitations(email);
CREATE INDEX idx_invitations_state ON invitations(state) WHERE state = 'pending';

CREATE TABLE refresh_tokens (                    -- rotation-on-use audit trail (NFR-5.2.2)
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash     TEXT NOT NULL UNIQUE,         -- SHA-256 of the opaque refresh token
    issued_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at     TIMESTAMPTZ NOT NULL,
    rotated_from   UUID REFERENCES refresh_tokens(id) ON DELETE SET NULL,
    revoked_at     TIMESTAMPTZ,                  -- rotation OR logout OR admin revoke
    revoked_reason TEXT,                         -- 'rotated' | 'logout' | future values
    user_agent     TEXT
);
CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_active
    ON refresh_tokens(user_id, expires_at) WHERE revoked_at IS NULL;

CREATE TABLE clients (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id),
    name            TEXT NOT NULL,
    contact_json    JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_clients_org ON clients(organization_id);

-- ================================================================
-- Projects & methodology
-- ================================================================
CREATE TABLE projects (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id       UUID REFERENCES organizations(id),
    client_id             UUID REFERENCES clients(id),
    key                   TEXT NOT NULL UNIQUE,          -- 'ACME-PORTAL'
    name                  TEXT NOT NULL,
    methodology           methodology NOT NULL,
    ai_enabled            BOOLEAN NOT NULL DEFAULT TRUE,
    llm_config            JSONB NOT NULL DEFAULT '{}',   -- typed via LLMConfig schema
    client_portal_mode    portal_mode NOT NULL DEFAULT 'export_only',
    start_date            DATE,
    target_date           DATE,
    status                TEXT NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active', 'on_hold', 'completed', 'cancelled')),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_projects_org ON projects(organization_id);
CREATE INDEX idx_projects_client ON projects(client_id);

CREATE TABLE project_members (
    project_id     UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id        UUID NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
    role           project_role NOT NULL,
    allocation_pct SMALLINT NOT NULL DEFAULT 100
                   CHECK (allocation_pct BETWEEN 0 AND 100),
    added_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, user_id)
);

-- ================================================================
-- Methodology configuration (data, not code)
-- ================================================================
CREATE TABLE workflow_states (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    key         TEXT NOT NULL,
    label       TEXT NOT NULL,
    category    TEXT NOT NULL CHECK (category IN ('todo', 'in_progress', 'done')),
    sort_order  SMALLINT NOT NULL DEFAULT 0,
    UNIQUE (project_id, key)
);

CREATE TABLE workflow_transitions (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id        UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    from_state        UUID NOT NULL REFERENCES workflow_states(id) ON DELETE CASCADE,
    to_state          UUID NOT NULL REFERENCES workflow_states(id) ON DELETE CASCADE,
    is_hard_gate      BOOLEAN NOT NULL DEFAULT FALSE,
    required_role     project_role,                       -- who may execute the transition
    approval_quorum   JSONB NOT NULL DEFAULT '{}',        -- {"project_owner": 1, "client_approver": 1}
    UNIQUE (project_id, from_state, to_state)
);

CREATE TABLE hierarchy_rules (
    project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    parent_kind work_item_kind NOT NULL,
    child_kind  work_item_kind NOT NULL,
    PRIMARY KEY (project_id, parent_kind, child_kind)
);

-- ================================================================
-- Sprints & milestones
-- ================================================================
CREATE TABLE sprints (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    goal       TEXT,
    starts_on  DATE NOT NULL,
    ends_on    DATE NOT NULL,
    state      TEXT NOT NULL DEFAULT 'planned'
               CHECK (state IN ('planned', 'active', 'closed')),
    CHECK (ends_on > starts_on)
);
CREATE INDEX idx_sprints_project ON sprints(project_id);

CREATE TABLE milestones (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id    UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    phase_kind    work_item_kind,                        -- set for waterfall gates ('phase')
    due_date      DATE,
    is_hard_gate  BOOLEAN NOT NULL DEFAULT FALSE,
    gate_status   gate_status NOT NULL DEFAULT 'pending',
    sort_order    SMALLINT NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_milestones_project ON milestones(project_id);

CREATE TABLE milestone_approvals (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    milestone_id      UUID NOT NULL REFERENCES milestones(id) ON DELETE CASCADE,
    user_id           UUID NOT NULL REFERENCES users(id),
    role_at_approval  project_role NOT NULL,
    decision          approval_decision NOT NULL,
    reason            TEXT,                              -- required when decision='reject'
    decided_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at        TIMESTAMPTZ,
    UNIQUE (milestone_id, user_id, revoked_at)           -- one active decision per user
);
CREATE INDEX idx_approvals_milestone ON milestone_approvals(milestone_id)
    WHERE revoked_at IS NULL;

-- ================================================================
-- Work items
-- ================================================================
CREATE TABLE work_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind            work_item_kind NOT NULL,
    parent_id       UUID REFERENCES work_items(id) ON DELETE SET NULL,
    seq             INTEGER NOT NULL,
    title           TEXT NOT NULL,
    description_md  TEXT NOT NULL DEFAULT '',
    acceptance_md   TEXT,
    state_id        UUID NOT NULL REFERENCES workflow_states(id),
    assignee_id     UUID REFERENCES users(id),
    sprint_id       UUID REFERENCES sprints(id),
    milestone_id    UUID REFERENCES milestones(id),
    story_points    NUMERIC(5,1),
    estimated_hours NUMERIC(7,2),
    actual_hours    NUMERIC(7,2),
    rank            TEXT,                                -- lexorank
    created_by      UUID NOT NULL REFERENCES users(id),
    ai_generated    BOOLEAN NOT NULL DEFAULT FALSE,
    source_job_id   UUID,                                -- FK added after ai_generation_jobs
    stale           BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, seq)
);
CREATE INDEX idx_wi_project_state  ON work_items(project_id, state_id);
CREATE INDEX idx_wi_parent         ON work_items(parent_id);
CREATE INDEX idx_wi_sprint         ON work_items(sprint_id);
CREATE INDEX idx_wi_milestone      ON work_items(milestone_id);
-- NOTE (M0.T5): a partial predicate with a subquery is invalid in Postgres index
-- definitions, so the "_open" partial index is shipped as a plain index. Revisit
-- with an app-maintained boolean column if open-item scans need the partial.
CREATE INDEX idx_wi_assignee       ON work_items(assignee_id);

CREATE TABLE work_item_links (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_item   UUID NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
    to_item     UUID REFERENCES work_items(id) ON DELETE CASCADE,
    to_chunk    UUID,                                    -- FK below
    link_type   link_type NOT NULL,
    CHECK (from_item <> to_item),
    CHECK (to_item IS NOT NULL OR to_chunk IS NOT NULL)
);
CREATE INDEX idx_links_from_type ON work_item_links(from_item, link_type);
CREATE INDEX idx_links_to_item   ON work_item_links(to_item);
CREATE INDEX idx_links_to_chunk  ON work_item_links(to_chunk);

-- ================================================================
-- Documents
-- ================================================================
CREATE TABLE documents (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id         UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    doc_type           doc_type NOT NULL,
    title              TEXT NOT NULL,
    current_version_id UUID,                             -- FK below
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_documents_project ON documents(project_id);

CREATE TABLE document_versions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id    UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    version_no     INTEGER NOT NULL,
    content_md     TEXT NOT NULL,
    content_hash   TEXT NOT NULL,                        -- SHA-256, for diff-based supersession
    status         doc_status NOT NULL DEFAULT 'draft',
    change_summary TEXT,
    created_by     UUID NOT NULL REFERENCES users(id),
    ai_job_id      UUID,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at    TIMESTAMPTZ,
    UNIQUE (document_id, version_no)
);
ALTER TABLE documents
    ADD CONSTRAINT fk_current_version
    FOREIGN KEY (current_version_id) REFERENCES document_versions(id);

CREATE UNIQUE INDEX idx_doc_one_approved
    ON document_versions(document_id) WHERE status = 'approved';

CREATE TABLE document_chunks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id          UUID NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    section_path        TEXT NOT NULL,
    content             TEXT NOT NULL,
    content_hash        TEXT NOT NULL,
    token_count         INTEGER NOT NULL,
    embedding           vector(768),
    embedding_model     TEXT,
    embedding_alt       vector(1536),
    embedding_alt_model TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_chunks_version ON document_chunks(version_id);
CREATE INDEX idx_chunks_embedding ON document_chunks
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)
    WHERE embedding IS NOT NULL;
CREATE INDEX idx_chunks_embedding_alt ON document_chunks
    USING hnsw (embedding_alt vector_cosine_ops) WITH (m = 16, ef_construction = 64)
    WHERE embedding_alt IS NOT NULL;

ALTER TABLE work_item_links
    ADD CONSTRAINT fk_link_chunk
    FOREIGN KEY (to_chunk) REFERENCES document_chunks(id) ON DELETE SET NULL;

-- ================================================================
-- Capacity
-- ================================================================
CREATE TABLE capacity_entries (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    sprint_id  UUID REFERENCES sprints(id),
    kind       capacity_kind NOT NULL,
    starts_on  DATE NOT NULL,
    ends_on    DATE NOT NULL,
    hours      NUMERIC(6,2),
    CHECK (ends_on >= starts_on)
);
CREATE INDEX idx_capacity_user_range ON capacity_entries(user_id, starts_on, ends_on);

-- ================================================================
-- AI jobs, provenance, stale flags
-- ================================================================
CREATE TABLE ai_generation_jobs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id              UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    requested_by            UUID NOT NULL REFERENCES users(id),
    agent_role              agent_role NOT NULL,
    target_artifact         artifact_type NOT NULL,
    focus_item_id           UUID REFERENCES work_items(id),
    instructions            TEXT,
    status                  job_status NOT NULL DEFAULT 'queued',
    retrieval_model         TEXT,                         -- 'nomic-embed-text-v1.5'
    model_used              TEXT,
    prompt_tokens           INTEGER,
    output_tokens           INTEGER,
    result_document_version UUID REFERENCES document_versions(id),
    error                   TEXT,
    trace_id                TEXT,
    heartbeat_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at              TIMESTAMPTZ,
    finished_at             TIMESTAMPTZ
);
CREATE INDEX idx_jobs_project_status ON ai_generation_jobs(project_id, status);
CREATE INDEX idx_jobs_running_heartbeat
    ON ai_generation_jobs(heartbeat_at) WHERE status = 'running';

ALTER TABLE work_items ADD CONSTRAINT fk_wi_source_job
    FOREIGN KEY (source_job_id) REFERENCES ai_generation_jobs(id);
ALTER TABLE document_versions ADD CONSTRAINT fk_dv_ai_job
    FOREIGN KEY (ai_job_id) REFERENCES ai_generation_jobs(id);

CREATE TABLE ai_provenance (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id        UUID NOT NULL REFERENCES ai_generation_jobs(id) ON DELETE CASCADE,
    stage         TEXT NOT NULL CHECK (stage IN ('lineage','semantic','operational')),
    source_chunk  UUID REFERENCES document_chunks(id) ON DELETE SET NULL,
    chunk_hash    TEXT,                                  -- denormalized survivor if chunk deleted
    section_path  TEXT,                                  -- denormalized survivor
    source_item   UUID REFERENCES work_items(id) ON DELETE SET NULL,
    similarity    REAL,
    CHECK (source_chunk IS NOT NULL OR source_item IS NOT NULL)
);
CREATE INDEX idx_provenance_job ON ai_provenance(job_id);

CREATE TABLE stale_flags (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    target_kind  TEXT NOT NULL CHECK (target_kind IN ('document','work_item')),
    target_id    UUID NOT NULL,
    triggered_by UUID REFERENCES document_versions(id),
    reason       stale_reason NOT NULL,
    detail_json  JSONB NOT NULL DEFAULT '{}',
    resolved_at  TIMESTAMPTZ,
    resolved_by  UUID REFERENCES users(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_stale_open ON stale_flags(project_id) WHERE resolved_at IS NULL;

-- ================================================================
-- Audit
-- ================================================================
CREATE TABLE audit_log (
    id         BIGSERIAL PRIMARY KEY,
    organization_id UUID,
    project_id UUID,
    actor_id   UUID,
    action     TEXT NOT NULL,
    entity     TEXT NOT NULL,
    entity_id  UUID,
    detail     JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_project_time ON audit_log(project_id, created_at DESC);
CREATE INDEX idx_audit_action       ON audit_log(action);

-- ================================================================
-- Signed export links (client_portal_mode='export_only')
-- ================================================================
CREATE TABLE signed_links (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id    UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    resource_kind TEXT NOT NULL CHECK (resource_kind IN ('roadmap_report','document_version')),
    resource_id   UUID NOT NULL,
    token_hash    TEXT NOT NULL,
    created_by    UUID NOT NULL REFERENCES users(id),
    expires_at    TIMESTAMPTZ NOT NULL,
    revoked_at    TIMESTAMPTZ,
    last_used_at  TIMESTAMPTZ,
    use_count     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_signed_active ON signed_links(project_id) WHERE revoked_at IS NULL;

-- ================================================================
-- Lineage helper (cycle-safe)
-- ================================================================
CREATE OR REPLACE FUNCTION lineage_chunks(_focus UUID, _max_depth INT DEFAULT 6)
RETURNS TABLE(chunk_id UUID, section_path TEXT, content TEXT, depth INT) AS $$
WITH RECURSIVE walk(item_id, depth, visited) AS (
    SELECT _focus, 0, ARRAY[_focus]::UUID[]
    UNION ALL
    SELECT l.to_item, w.depth + 1, w.visited || l.to_item
    FROM walk w
    JOIN work_item_links l ON l.from_item = w.item_id
    WHERE l.link_type = 'derived_from'
      AND l.to_item IS NOT NULL
      AND NOT (l.to_item = ANY(w.visited))
      AND w.depth < _max_depth
),
chunks AS (
    SELECT DISTINCT l.to_chunk AS chunk_id, w.depth
    FROM walk w
    JOIN work_item_links l ON l.from_item = w.item_id
    WHERE l.link_type = 'derived_from' AND l.to_chunk IS NOT NULL
)
SELECT c.id, c.section_path, c.content, ch.depth
FROM chunks ch
JOIN document_chunks c ON c.id = ch.chunk_id
ORDER BY ch.depth ASC;
$$ LANGUAGE SQL STABLE;
```

### 2.3 Migration ordering notes
- Enum creation before tables.
- Circular FK between `documents ↔ document_versions` resolved by adding `documents.current_version_id` constraint after both tables exist.
- Circular FK between `work_items ↔ ai_generation_jobs` resolved by deferring the `fk_wi_source_job` constraint.
- Advisory lock at Alembic upgrade: `SELECT pg_advisory_xact_lock(hashtext('krititva-migrations'))` **inside** `context.begin_transaction()`. This is a transaction-scoped lock — auto-released on COMMIT or ROLLBACK. Do NOT use the session-scoped `pg_advisory_lock` with a finally-block unlock: on a failed migration, the transaction is aborted and the unlock call itself raises `InFailedSQLTransactionError`, masking the real error.
- **Enums referenced inside `op.create_table` MUST use `postgresql.ENUM(..., create_type=False)` — never `sa.Enum(..., create_type=False, native_enum=True)`.** The generic `sa.Enum` path emits a spurious `CREATE TYPE` inside `op.create_table` on SQLAlchemy 2.0.51, producing `DuplicateObjectError` on the migration that owns the type. See [`.claude/skills/krititva-migration/SKILL.md`](../.claude/skills/krititva-migration/SKILL.md) for the helper pattern.

---

## 3. Domain Model & Service Contracts

### 3.1 Service class contracts

Services are stateful only in the sense that they hold an `AsyncSession`. All methods are `async`. All raise typed exceptions caught by `api/errors.py` and mapped to HTTP.

```python
# app/services/work_items.py
class WorkItemService:
    def __init__(self, db: AsyncSession, audit: AuditSink) -> None: ...

    async def create(self, project_id: UUID, actor_id: UUID,
                     payload: WorkItemCreate) -> WorkItem: ...

    async def transition(self, item_id: UUID, actor_id: UUID,
                         to_state_id: UUID) -> WorkItem:
        """Enforce state machine + hard-gate. Raises:
           - HierarchyViolation
           - InvalidTransition
           - GateNotApproved
           - InsufficientRole
        """

    async def link(self, from_id: UUID, to_id: UUID | None,
                   to_chunk_id: UUID | None, link_type: LinkType) -> WorkItemLink:
        """Raises CycleDetected for derived_from cycles."""

    async def rerank(self, item_id: UUID, before_id: UUID | None,
                     after_id: UUID | None) -> WorkItem: ...

    async def bulk_transition(self, ids: list[UUID], to_state_id: UUID,
                              actor_id: UUID) -> BulkResult:
        """Per-item auth, per-item error. Never partially transactional across items."""
```

```python
# app/services/documents.py
class DocumentService:
    async def create(self, project_id: UUID, doc_type: DocType, title: str,
                     actor_id: UUID) -> Document: ...

    async def create_version(self, document_id: UUID, actor_id: UUID,
                             content_md: str, base_version_id: UUID | None,
                             change_summary: str | None,
                             ai_job_id: UUID | None) -> DocumentVersion:
        """Optimistic lock on base_version_id. Enqueues chunk+embed job.
           Raises VersionConflict on stale base."""

    async def approve(self, version_id: UUID, actor_id: UUID) -> DocumentVersion:
        """Enforces single-approved-per-document invariant. Supersedes prior."""

    async def get_chunks_for_retrieval(self, project_id: UUID,
                                       doc_types: list[DocType],
                                       embedding_model: str) -> list[Chunk]: ...
```

```python
# app/services/approvals.py
class ApprovalService:
    async def record(self, milestone_id: UUID, actor_id: UUID,
                     decision: Decision, reason: str | None) -> MilestoneApproval:
        """Recomputes gate_status after write. Raises:
           - RejectRequiresReason
           - InsufficientRoleForQuorum
        """

    async def revoke(self, approval_id: UUID, actor_id: UUID) -> None: ...

    async def quorum_met(self, milestone_id: UUID) -> bool: ...
```

```python
# app/services/ai_orchestrator.py
class AIOrchestrator:
    async def enqueue(self, project_id: UUID, actor_id: UUID,
                      req: GenerateArtifactRequest) -> UUID:
        """Returns job_id. Raises:
           - AIDisabled
           - AgentDisabled
           - CannotProduceArtifact
           - PrereqNotApproved
           - TooManyInFlight
        """

    async def stream(self, job_id: UUID) -> AsyncIterator[SSEEvent]: ...
    async def accept(self, job_id: UUID, actor_id: UUID) -> AcceptResult: ...
    async def reject(self, job_id: UUID, actor_id: UUID, reason: str) -> None: ...
```

### 3.2 Error taxonomy → HTTP

| Exception | HTTP | Payload code | Notes |
|---|---|---|---|
| `NotFound` | 404 | `not_found` | Membership disclosure suppressed |
| `HierarchyViolation` | 422 | `hierarchy_violation` | Includes `parent_kind`, `child_kind` |
| `InvalidTransition` | 422 | `invalid_transition` | Includes `from_state`, `to_state` |
| `GateNotApproved` | 409 | `gate_not_approved` | Includes `milestone_id`, `quorum` |
| `InsufficientRole` | 403 | `insufficient_role` | For explicit role denials only |
| `CycleDetected` | 422 | `link_cycle_detected` | Includes cycle path |
| `VersionConflict` | 409 | `version_conflict` | Includes head `version_id` and diff |
| `AIDisabled` | 403 | `ai_disabled` | Per-project |
| `AgentDisabled` | 403 | `agent_disabled` | Per-agent |
| `CannotProduceArtifact` | 422 | `role_artifact_mismatch` | |
| `PrereqNotApproved` | 409 | `prereq_missing` | List of missing doc types |
| `TooManyInFlight` | 429 | `job_concurrency_limit` | With `Retry-After` |
| `RejectRequiresReason` | 422 | `reason_required` | |

---

## 4. API Surface (definitive endpoints)

Base URL: `/api/v1`. All state-changing endpoints require `X-CSRF-Token` (browser) or bearer JWT (client). All responses are `application/json` except SSE at `text/event-stream`.

### 4.1 Auth
```
POST   /auth/login                     -> {access, refresh}
POST   /auth/refresh                   -> {access, refresh}
POST   /auth/logout                    -> 204
POST   /auth/invitations               -> {invitation_id}     [org_admin | project_owner]
POST   /auth/invitations/accept        -> {access, refresh}   [public, token-bearing]
GET    /auth/me                        -> {user, org, memberships}
```

### 4.2 Projects & config
```
GET    /projects                       -> [Project]           (org_admin: all org; else memberships)
POST   /projects                       -> Project             [org_admin | project_owner-role]
GET    /projects/{id}                  -> Project
PATCH  /projects/{id}                  -> Project             [project_owner]
PUT    /projects/{id}/llm-config       -> LLMConfig           [project_owner | org_admin]
POST   /projects/{id}/members          -> ProjectMember
DELETE /projects/{id}/members/{uid}    -> 204
```

### 4.3 Methodology
```
GET    /projects/{id}/workflow/states                          -> [WorkflowState]
GET    /projects/{id}/workflow/transitions                     -> [WorkflowTransition]
PATCH  /projects/{id}/workflow/transitions/{tid}               -> WorkflowTransition
GET    /projects/{id}/hierarchy-rules                          -> [HierarchyRule]
PATCH  /projects/{id}/hierarchy-rules                          -> [HierarchyRule] (replace-all)
```

### 4.4 Work items
```
POST   /projects/{id}/work_items                               -> WorkItem
GET    /projects/{id}/work_items?filters=...                   -> Paginated[WorkItem]
GET    /projects/{id}/work_items/{wid}                         -> WorkItem
PATCH  /projects/{id}/work_items/{wid}                         -> WorkItem
POST   /projects/{id}/work_items/{wid}/transitions             -> WorkItem
POST   /projects/{id}/work_items/{wid}/links                   -> WorkItemLink
POST   /projects/{id}/work_items/bulk-transition               -> BulkResult
GET    /projects/{id}/work_items/{wid}/lineage                 -> [LineageNode]
```

### 4.5 Sprints & capacity
```
POST   /projects/{id}/sprints                                  -> Sprint
GET    /projects/{id}/sprints/{sid}/capacity                   -> CapacityView
POST   /users/{uid}/capacity-entries                           -> CapacityEntry
```

### 4.6 Milestones & approvals
```
POST   /projects/{id}/milestones                               -> Milestone
GET    /projects/{id}/milestones                               -> [Milestone]
POST   /projects/{id}/milestones/{mid}/approvals               -> MilestoneApproval
DELETE /projects/{id}/milestones/{mid}/approvals/{aid}         -> 204   (revoke)
```

### 4.7 Documents
```
POST   /projects/{id}/documents                                -> Document
POST   /projects/{id}/documents/{did}/versions                 -> DocumentVersion
POST   /projects/{id}/documents/{did}/versions/{vid}/approve   -> DocumentVersion
GET    /projects/{id}/documents/{did}/export.pdf               -> application/pdf
```

### 4.8 AI artifacts
```
POST   /projects/{id}/artifacts                                -> {job_id} (202)
GET    /projects/{id}/artifacts/jobs/{jid}                     -> JobStatus
GET    /projects/{id}/artifacts/jobs/{jid}/events              -> text/event-stream
POST   /projects/{id}/artifacts/jobs/{jid}/accept              -> AcceptResult
POST   /projects/{id}/artifacts/jobs/{jid}/reject              -> 204
GET    /projects/{id}/artifacts/jobs/{jid}/provenance          -> [ProvenanceEntry]
GET    /projects/{id}/stale-flags                              -> [StaleFlag]
```

### 4.9 Reports & client portal
```
GET    /projects/{id}/reports/roadmap-vs-milestone             -> ReportView
POST   /projects/{id}/signed-links                             -> {url, expires_at}
GET    /public/signed/{token}                                  -> ReportView | DocumentVersion
```

### 4.10 Audit
```
GET    /projects/{id}/audit-log?since=...                      -> Paginated[AuditEntry]
GET    /projects/{id}/audit-log/export.jsonl                   -> application/x-jsonlines
```

---

## 5. AI Subsystem — Concrete Design

### 5.1 Profile protocol

```python
# app/ai/profiles/base.py
from typing import Protocol
from pydantic import BaseModel

class RoleProfile(Protocol):
    role: agent_role
    artifacts: set[artifact_type]
    model_tier: str                                  # 'frontier' | 'mid' | 'fast'
    output_schema: type[BaseModel]

    async def retrieval_policy(self, db, project, focus_item) -> RetrievalPlan: ...
    def render_system(self, assembled: AssembledContext) -> str: ...
    def render_user(self, assembled: AssembledContext, instructions: str | None) -> str: ...
    async def persist_draft(self, db, job, artifact: BaseModel) -> PersistResult: ...
```

### 5.2 Retrieval plan

```python
@dataclass
class RetrievalPlan:
    include_lineage: bool = True
    lineage_max_depth: int = 6
    semantic_doc_types: list[DocType] = field(default_factory=list)
    semantic_k: int = 20
    include_operational: bool = False
    operational_scope: set[str] = field(default_factory=set)   # 'sprint','capacity','open_items'
    token_budget: int = 12000
```

### 5.3 Context Assembler algorithm

```
INPUT: project, profile, focus_item_id
1.  plan = await profile.retrieval_policy(db, project, focus_item)
2.  If plan.include_lineage and focus_item_id:
      lineage_chunks = SELECT * FROM lineage_chunks(focus_item_id, plan.lineage_max_depth)
    Else:
      lineage_chunks = []
3.  query_text = focus_item.title + '\n' + focus_item.description_md   (or job.instructions when no focus)
    query_vec = await embed(query_text, project.llm_config.retrieval_model)
4.  used_ids = set(c.id for c in lineage_chunks)
    semantic = SELECT ... FROM document_chunks c
               JOIN document_versions v ON v.id = c.version_id
               JOIN documents d ON d.current_version_id = v.id
               WHERE d.project_id = project.id
                 AND d.doc_type = ANY(plan.semantic_doc_types)
                 AND c.embedding_model = project.llm_config.retrieval_model
                 AND c.id NOT IN used_ids
               ORDER BY c.embedding <=> query_vec
               LIMIT plan.semantic_k
5.  operational = if plan.include_operational: fetch_operational(plan.operational_scope)
6.  packed = pack_to_budget(lineage_chunks, semantic, operational, budget=plan.token_budget)
7.  persist_provenance(job, stage='lineage'|'semantic'|'operational', ...)  BEFORE returning
8.  return AssembledContext(packed)
```

Packing policy: lineage never dropped (overflow triggers `summarize_lineage_fallback`); semantic dropped from tail; operational dropped from tail.

### 5.4 Role profiles — concrete config

| Role | Artifacts | Semantic doc_types | Operational | Token budget | Model tier | Output schema |
|---|---|---|---|---|---|---|
| Project Owner | `srs`, `epic_breakdown` | project prior notes | none | 16000 | frontier | `SRSDocument`, `EpicBreakdown` |
| Architect | `hld`, `lld` | `srs`, `hld` | none | 24000 | frontier | `DesignDocument` |
| Scrum Master | `sprint_plan`, `story_breakdown` | `srs` (via lineage) | `sprint`+`capacity`+`open_items` | 12000 | mid | `SprintPlan`, `StoryBreakdown` |
| Developer | `task_breakdown`, `api_contract` | `srs`, `lld` | `open_items` | 12000 | mid | `TaskBreakdown`, `APIContract` |
| QA | `test_plan`, `test_cases` | `srs`, `lld` | none | 12000 | mid (high volume) | `TestPlan`, `TestCaseSet` |

### 5.5 Pydantic output schemas (representative)

```python
# app/schemas/artifacts.py
class MermaidDiagram(BaseModel):
    caption: str = Field(max_length=200)
    code: str = Field(max_length=8000)

class DesignSection(BaseModel):
    heading: str
    section_path: str                                  # '3.2.1'
    body_md: str
    srs_citations: list[str] = Field(default_factory=list)   # e.g. ['[SRS §4.6.9]']
    open_questions: list[str] = Field(default_factory=list)

class DesignDocument(BaseModel):
    title: str
    scope_summary: str
    sections: list[DesignSection]
    mermaid_diagrams: list[MermaidDiagram] = Field(default_factory=list)

class AcceptanceCriterion(BaseModel):
    text: str
    kind: Literal['functional','edge','negative'] = 'functional'

class StoryDraft(BaseModel):
    title: str = Field(max_length=140)
    description_md: str
    acceptance: list[AcceptanceCriterion]
    story_points: float | None = None
    estimated_hours: float | None = None
    srs_citations: list[str]

class StoryBreakdown(BaseModel):
    epic_id: UUID
    stories: list[StoryDraft]

class TestCase(BaseModel):
    title: str
    preconditions_md: str
    steps: list[str]
    expected_md: str
    kind: Literal['functional','edge','negative','regression'] = 'functional'
    srs_citations: list[str]
    story_id: UUID | None = None

class TestCaseSet(BaseModel):
    story_id: UUID
    cases: list[TestCase]
```

### 5.6 LLM client wrapper

```python
# app/ai/llm_client.py
class LLMClient:
    async def acompletion(
        self,
        *, model: str, messages: list[Msg], response_format: type[BaseModel],
        metadata: dict, timeout_s: int = 300,
    ) -> LLMResult:
        """Wraps litellm.acompletion. Retries: schema-parse failure -> reprompt with
        error appended (max 2 attempts). Timeouts propagate as LLMTimeout."""
```

### 5.7 SSE bridging

- Worker publishes JSON frames to Redis channel `job:{job_id}` throughout run.
- API `stream` endpoint subscribes to the channel, emits SSE frames as they arrive.
- API also emits a 15 s heartbeat frame (`event: heartbeat`).
- On subscribe, API first sends the last known job state as an SSE frame so late subscribers are not stranded.
- Worker crash detection: `worker_heartbeat_sweeper` cron scans `ai_generation_jobs WHERE status='running' AND heartbeat_at < now() - '60 seconds'`, sets status to `failed`, publishes a terminal frame.

---

## 6. State Machines (concrete)

### 6.1 Document version status

```
draft ─── submit ───▶ in_review ─── approve ───▶ approved
  ▲                        │                          │
  │                        └── request_changes ─── ▶ draft
  │                                                   │
  │                                                   ▼
  └──────── (new version created) ──────── superseded
```

### 6.2 AI job status

```
queued ─▶ running ─▶ awaiting_review ─▶ accepted
                          │                 
                          ├── reject ────▶ rejected
                          │                 
running ─── failure ────▶ failed
running ─── heartbeat missed ▶ failed
```

### 6.3 Milestone gate

```
pending ─▶ in_review ─── quorum satisfied ────▶ approved
   ▲            │                                 
   │            └── any_reject ─▶ rejected        
   │                                              
   └── revoke_all_approvals ──────────────────────
```

### 6.4 Work item generic (Agile default)

```
backlog ─▶ in_progress ─▶ in_review ─▶ qa ─▶ done
             │ ▲           │ ▲         │ ▲
             ▼ │           ▼ │         ▼ │
             (any → blocked, blocked → previous)
```

### 6.5 Waterfall phase gate

```
not_started ─▶ in_progress ─▶ gate_review ── hard_gate ─▶ done
```

---

## 7. Frontend Architecture (concrete)

### 7.1 Route map (Next.js App Router)

> M0.T6 delta: the dynamic project segment is implemented as `[projectId]` (UUID),
> not `[key]`. Every backend endpoint is id-addressed and there is no key→id
> lookup, so the URL carries the id and the UI shows the human key. Revisit if a
> `GET /projects?key=` resolver is added.

```
/                                       Marketing / login redirect
/setup                                  First-run bootstrap (org_admin)
/login  /invite/[token]  /callback      Auth flows
/(app)/dashboard                        Cross-project widget grid
/(app)/projects                         Project list
/(app)/projects/[key]/                  Project home
/(app)/projects/[key]/board             Kanban / sprint board
/(app)/projects/[key]/backlog           Prioritized backlog
/(app)/projects/[key]/documents         Doc index
/(app)/projects/[key]/documents/[did]   Editor + AI panel
/(app)/projects/[key]/roadmap           Gantt / milestone view
/(app)/projects/[key]/settings          Methodology, LLM config, portal
/(portal)/shared/[token]                Client-portal export view
```

### 7.2 Shared components (shadcn/ui composition)

- `AIPanel` — drafts, provenance list, accept/reject actions, SSE-driven progress.
- `WorkItemDialog` — form + hierarchy + link editor + transition button (gate-aware).
- `DocumentEditor` — TipTap Markdown, Mermaid preview, version history side panel.
- `RoadmapView` — milestones + phases (Waterfall) or milestones + sprints (Agile), export to PDF.
- `ApprovalBar` — multi-sig quorum tracker.

### 7.3 State management
- Server state: TanStack Query with per-endpoint cache keys.
- Client state: minimal Zustand stores only for UI-local flags (open dialogs, filter presets).
- Optimistic mutations for board drag/transition, rolled back on 409/422 with toast.

### 7.4 Generated API client
- Emitted from FastAPI's OpenAPI at build time into `packages/api-client/`.
- Consumed by `apps/web` via workspace dependency.

---

## 8. Deployment Config

### 8.1 docker-compose.yml (structural summary)

```yaml
services:
  web:      image: krititva/web:${VERSION}   depends_on: [api]
  api:      image: krititva/api:${VERSION}   depends_on: [postgres, redis]
  worker:   image: krititva/api:${VERSION}   command: ["arq","app.workers.arq_settings.WorkerSettings"]
            depends_on: [postgres, redis, litellm]
  postgres: image: pgvector/pgvector:pg16    volumes: [pgdata:/var/lib/postgresql/data]
  redis:    image: redis:7-alpine            command: ["redis-server","--appendonly","yes"]
            volumes: [redisdata:/data]
  litellm:  image: ghcr.io/berriai/litellm:main
            volumes: ["./litellm.config.yaml:/app/config.yaml"]
  langfuse: image: langfuse/langfuse:latest   profiles: ["obs"]   # opt-in
volumes: {pgdata: {}, redisdata: {}, assets: {}}
```

### 8.2 Env vars (canonical)
```
POSTGRES_DSN=postgresql+asyncpg://...
REDIS_URL=redis://redis:6379/0
LITELLM_URL=http://litellm:4000
KRITITVA_DATA_KEY=<32-byte base64>          # AES-256 for at-rest secrets
KRITITVA_TELEMETRY_ENABLED=false            # default off
KRITITVA_PUBLIC_BASE_URL=https://...        # for signed links
SMTP_URL=smtp://...                          # optional
OIDC_ISSUER=https://...                     # optional
```

---

## 9. Testing Strategy

### 9.1 Coverage targets (§NFR-5.4.3)
- Work Item Engine: ≥ 90% line, 100% branch on state machine.
- Approval Engine: 100% branch on quorum evaluation.
- Context Assembler: ≥ 90% line, focus on packing/overflow edge cases.

### 9.2 Test kinds
- **Unit** — pytest, `pytest-asyncio`, transactional test DB (SAVEPOINT per test).
- **Contract** — golden-file tests for OpenAPI diff; Pydantic schema roundtrips.
- **Integration** — spins ephemeral Postgres+Redis via testcontainers.
- **AI** — deterministic fake LLM (`FakeLLMClient`) returns fixture responses per profile; a small "smoke suite" runs against real Ollama in CI on tagged releases only.
- **E2E** — Playwright against docker-compose stack.

### 9.3 CI gates
- `ruff` + `mypy --strict` (backend).
- `eslint` + `tsc --noEmit` (frontend).
- Unit + contract on every PR; integration + Playwright on main.
- OpenAPI diff check with human-readable diff comment on PR.
- SBOM + license audit (fail on non-permissive/non-AGPL-compatible new deps).

---

## 10. Boilerplate: `generate_project_artifact` (definitive)

Blueprint §6 code stands with these deltas applied:
- Prerequisite check reads `documents WHERE status='approved'` explicitly, not "current version exists".
- Per-user concurrency check via Redis semaphore (§NFR-5.2.5).
- `retrieval_model` recorded on the job at enqueue time (immutability of the retrieval config for reproducibility).
- Worker sets `heartbeat_at = now()` on entry to `running` and periodically during long calls.

```python
# app/api/routes/artifacts.py  (delta only)
@router.post("", response_model=GenerateArtifactResponse,
             status_code=status.HTTP_202_ACCEPTED)
async def generate_project_artifact(
    project_id: UUID, body: GenerateArtifactRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    arq=Depends(get_arq_pool),
    limiter=Depends(get_user_ai_semaphore),
):
    project = await project_svc.get_for_member(db, project_id, user.id)
    if project is None:
        raise HTTPException(404, "not_found")
    if not project.ai_enabled:
        raise HTTPException(403, "ai_disabled")
    if body.agent_role.value in project.llm_config.get("disabled_agents", []):
        raise HTTPException(403, "agent_disabled")

    if body.target_artifact not in ROLE_ARTIFACTS[body.agent_role]:
        raise HTTPException(422, "role_artifact_mismatch")

    membership = await project_svc.get_membership(db, project_id, user.id)
    if not project_svc.may_invoke_agent(membership.role, body.agent_role):
        raise HTTPException(403, "insufficient_role")

    missing = await doc_svc.missing_approved_docs(
        db, project_id, ARTIFACT_PREREQS.get(body.target_artifact, set()))
    if missing:
        raise HTTPException(409, {"code": "prereq_missing", "missing": sorted(missing)})

    if not await limiter.try_acquire(user.id):
        raise HTTPException(429, "job_concurrency_limit",
                            headers={"Retry-After": "10"})

    job = AIGenerationJob(
        project_id=project_id, requested_by=user.id,
        agent_role=body.agent_role.value,
        target_artifact=body.target_artifact.value,
        focus_item_id=body.focus_item_id,
        instructions=body.instructions,
        retrieval_model=project.llm_config.get("retrieval_model", "nomic-embed-text-v1.5"),
    )
    db.add(job)
    await audit.write(db, project_id, user.id, "ai.job_created", "ai_job", job.id)
    await db.commit()
    await arq.enqueue_job("run_artifact_generation", str(job.id))
    return GenerateArtifactResponse(job_id=job.id)
```

Worker delta from blueprint (heartbeat + provenance-before-call already in blueprint):

```python
# app/workers/generation.py  (delta)
async def run_artifact_generation(ctx, job_id: str):
    async with session_scope() as db:
        job = await db.get(AIGenerationJob, job_id)
        job.status = "running"
        job.started_at = utcnow()
        job.heartbeat_at = utcnow()
        await db.commit()

    heartbeat = asyncio.create_task(_heartbeat_loop(job_id))
    try:
        async with session_scope() as db:
            profile = PROFILE_REGISTRY.resolve(job.agent_role, job.target_artifact)
            assembled = await ContextAssembler(db).assemble(
                project_id=job.project_id, profile=profile, focus_item_id=job.focus_item_id,
            )
            await assembled.persist_provenance(db, job.id)
            await db.commit()

        model = await resolve_model(db, job.project_id, profile.model_tier)
        result = await LLMClient().acompletion(
            model=model,
            messages=[
                {"role": "system", "content": profile.render_system(assembled)},
                {"role": "user",   "content": profile.render_user(assembled, job.instructions)},
            ],
            response_format=profile.output_schema,
            metadata={"trace_id": str(job_id)},
        )

        async with session_scope() as db:
            persisted = await profile.persist_draft(db, job, result.artifact)
            job.status = "awaiting_review"
            job.result_document_version = persisted.version_id
            job.model_used = result.model
            job.prompt_tokens = result.prompt_tokens
            job.output_tokens = result.output_tokens
            job.finished_at = utcnow()
            await audit.write(db, job.project_id, job.requested_by,
                              "ai.draft_persisted", "ai_job", job.id,
                              {"draft": str(persisted.version_id)})
            await db.commit()
        await publish_terminal(job_id, {"step": "done", "draft_id": str(persisted.version_id)})
    except Exception as exc:
        async with session_scope() as db:
            job.status = "failed"
            job.error = str(exc)[:2000]
            job.finished_at = utcnow()
            await db.commit()
        await publish_terminal(job_id, {"step": "failed", "error": str(exc)[:200]})
    finally:
        heartbeat.cancel()
```

---

## 11. LLM Config (typed)

```python
# app/schemas/llm_config.py
class LLMConfig(BaseModel):
    retrieval_model: str = "nomic-embed-text-v1.5"
    generation_models: dict[Literal["frontier","mid","fast"], str] = Field(
        default_factory=lambda: {
            "frontier": "ollama/qwen2.5:32b-instruct",
            "mid":      "ollama/qwen2.5:7b-instruct",
            "fast":     "ollama/llama3.2:3b-instruct",
        }
    )
    disabled_agents: list[agent_role] = Field(default_factory=list)
    tech_constraints: str | None = None          # free text passed to Architect
    provider_overrides: dict[str, str] = Field(default_factory=dict)  # {'anthropic': 'claude-...'}
```

Change endpoint audits every field diff.

---

## 12. Traceability

Each `FR-*` / `NFR-*` from the SRS resolves to at least one:
- Table + column (data model), and
- Service method (behavior), and
- API endpoint (surface), and
- Test module (coverage).

CI generates the `.planning/traceability.jsonl` manifest by parsing SRS + LLD headings and grepping for the referenced anchors in source files. A missing anchor fails CI (§OR-6.3.1).
