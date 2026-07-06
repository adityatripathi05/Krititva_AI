# Krititva AI — Software Requirements Specification (v1.0)

**Status:** Draft for review
**Upstream:** [krititva-ai-blueprint.md](krititva-ai-blueprint.md) v0.2 + resolved architect questions
**Downstream:** [krititva-hld.md](krititva-hld.md), [krititva-lld.md](krititva-lld.md), [krititva-roadmap.md](krititva-roadmap.md)

Every functional requirement carries a stable ID of the form `FR-<section>.<n>` and every non-functional requirement `NFR-<section>.<n>`. These IDs are the traceability anchors used by HLD sections, work items, and test cases.

---

## 1. Introduction

### 1.1 Purpose
This document specifies the software requirements for **Krititva AI**, an open-source, self-hostable project management platform for software agencies and services firms. Krititva AI supports both Waterfall and Agile methodologies on a per-project basis and integrates a contextual multi-agent AI layer that generates and maintains the full artifact chain — SRS → Epics → HLD/LLD → User Stories → Tasks → Test Cases — with end-to-end traceability.

### 1.2 Scope
Krititva AI v1 covers: identity and RBAC, client and project management, methodology-configurable work item engine, versioned document management with embeddings, five AI role agents in draft-and-review mode, milestone/gate approvals with multi-signature support, sprint and capacity tracking, one roadmap-vs-milestone report, and a Docker-Compose self-hosting story.

Explicit v1 non-goals (deferred, not rejected): full capacity planning with velocity modeling, critical path forward/backward pass, autonomous AI actions, GitHub/GitLab/Slack integrations, real-time collaborative editing (CRDTs), native mobile apps, Gantt auto-scheduling, time tracking, and billing.

### 1.3 Definitions, Acronyms, and Abbreviations
| Term | Meaning |
|---|---|
| SRS | Software Requirements Specification |
| HLD / LLD | High-Level Design / Low-Level Design |
| Work item | Any unit of work: phase, epic, feature, story, task, bug, deliverable, test case |
| Methodology profile | The bundle of allowed work-item kinds, hierarchy rules, and state machines applied to a project |
| Hard gate | A state transition requiring an approved milestone with a satisfied approval quorum |
| Role agent | A configured AI profile (retrieval policy + system template + output schema + model tier) that generates a specific artifact class |
| Provenance | The exact set of document chunks and work items an AI generation consumed |
| Lineage | The `derived_from`-typed link chain from a work item back to source SRS chunks |
| Draft-and-review | The mandatory workflow whereby every AI output is persisted as a draft and only becomes canonical after human acceptance |

### 1.4 References
- Blueprint v0.2: [krititva-ai-blueprint.md](krititva-ai-blueprint.md)
- IEEE Std 830-1998 (structural inspiration, not strict conformance)
- pgvector documentation (HNSW index parameters)
- LiteLLM gateway documentation (routing, budgets)
- Ollama HTTP API (structured output via `format`)

### 1.5 Overview
Section 2 describes the product context. Sections 3 and 4 define external interfaces and functional requirements. Section 5 defines non-functional requirements. Section 6 covers compliance, licensing, and operational constraints.

---

## 2. Overall Description

### 2.1 Product Perspective
Krititva AI is a standalone, self-contained product, not a plugin to an existing PM tool. It runs on-premises or on customer-controlled infrastructure. It does not depend on external SaaS by default; a fully local Ollama deployment satisfies every functional requirement in this document. Optional integrations (SSO IdPs, external LLM providers) are opt-in and configured per organization.

### 2.2 Product Functions (top-level)
1. Manage clients, projects, teams, and per-project methodology.
2. Manage the work item lifecycle (create, hierarchy, state transitions, assignments) under a configurable state machine and hierarchy ruleset.
3. Manage versioned Markdown documents (SRS/HLD/LLD/Test Plans) with section-aware chunking and vector embeddings on every save.
4. Orchestrate role-based AI generation of artifacts from context assembled by lineage + semantic retrieval; persist as drafts.
5. Manage approvals for milestones and gates with configurable multi-signature quorum rules.
6. Track sprints and simple per-sprint available hours.
7. Report roadmap vs. milestone achievement, shareable with clients under configurable modes.
8. Provide a full audit and provenance trail for every gate approval, AI generation, and draft acceptance.
9. Self-host via one `docker compose up`.

### 2.3 User Classes and Characteristics

| Class | Description | Frequency of use | Technical expertise |
|---|---|---|---|
| Organization admin | Configures org-level settings, LLM keys, SSO, licensing | Low | High |
| Project owner | Owns the project; can invoke any agent role; approves gates on behalf of the agency | High | Medium |
| Scrum Master | Runs sprints, invokes Scrum Master and Developer agents | High | Medium |
| Developer | Executes tasks, invokes Developer agent for breakdown/APIs | High | Medium/High |
| QA Engineer | Manages test plans and cases; invokes QA agent | High | Medium |
| Viewer (internal) | Reads work items and documents; no write permissions | Medium | Low |
| Client stakeholder | External to the agency; per-project access modes (none / export-only / portal); can co-sign gate approvals when portal mode is enabled | Low | Low |
| Contributor / plugin author | Extends the AI role profile plugin surface; does not necessarily hold a project role | Low | High |

### 2.4 Operating Environment
- Server-side: Linux (x86_64 and arm64), Docker Engine 24+, Docker Compose v2.
- Client-side: modern evergreen browsers (Chrome, Firefox, Safari, Edge — current and one previous major version). No IE support.
- LLM runtime: Ollama, vLLM, LM Studio, or any OpenAI-compatible endpoint. Frontier hosted models are optional and reachable only when the organization opts in and provides keys.

### 2.5 Design and Implementation Constraints
- Backend built from scratch in Python 3.12 (FastAPI + SQLAlchemy 2.0 async).
- Frontend assembled from mature OSS primitives (Next.js 15, shadcn/ui, TipTap, Mermaid.js, dnd-kit).
- One database technology (PostgreSQL 16 + pgvector); no separate vector store.
- Redis is the only additional runtime dependency, used for arq job queueing and SSE pub/sub bridging.
- No LLM weights are redistributed; models are pulled at first run.
- License: AGPL-3.0 for the core; contributions under DCO/lightweight CLA.
- No proprietary dependencies in the default install.

### 2.6 Assumptions and Dependencies
- Organizations self-host and are responsible for their own backups, TLS termination, and IdP configuration.
- The default embedding model is `nomic-embed-text` v1.5 (Apache-2.0, 768 dims). Alternate embedding models are supported via a discriminated embedding-model column.
- The default generation model tier is small local models (~8B class) on 8 GB VRAM for high-volume agents; ~30B class models for the Architect tier on 24 GB VRAM.
- Full offline operation is a supported deployment mode; no phone-home telemetry is enabled by default.

---

## 3. External Interface Requirements

### 3.1 User Interfaces
- **UI-1**: Web SPA built on Next.js 15, accessible at the API host's domain (default: `/`).
- **UI-2**: WCAG 2.1 AA target for core screens (project dashboard, work item board, document editor, roadmap view).
- **UI-3**: Markdown-first document editor (TipTap) with live Mermaid.js preview.
- **UI-4**: Kanban board (dnd-kit) for work items with lexorank-based drag ordering.
- **UI-5**: A dedicated AI panel per document/work item showing pending drafts, provenance, and accept/reject actions.

### 3.2 Hardware Interfaces
None mandated. Minimum recommended server: 4 vCPU / 16 GB RAM / 100 GB SSD for a small team without local LLM. With local LLM (8B class), add one GPU with 8+ GB VRAM or accept CPU inference latency.

### 3.3 Software Interfaces
- **SI-1** PostgreSQL 16 with `vector` and `pgcrypto` extensions.
- **SI-2** Redis 7 for arq queue and SSE pub/sub.
- **SI-3** LiteLLM gateway providing an OpenAI-compatible interface to Ollama, vLLM, LM Studio, Anthropic, OpenAI, and any other supported provider.
- **SI-4** Langfuse (self-hosted) for AI generation traces. Optional but recommended.
- **SI-5** SMTP for email notifications and client invitations (optional; disabled in a "no external egress" install).
- **SI-6** OIDC IdP for SSO (optional).

### 3.4 Communications Interfaces
- **CI-1** HTTPS for all external traffic. Self-hosted TLS termination is the operator's responsibility.
- **CI-2** REST + OpenAPI 3.1 for the primary API surface.
- **CI-3** Server-Sent Events (SSE) endpoint for AI job progress streaming.
- **CI-4** WebSocket surface is **out of scope for v1** (SSE is preferred for one-way progress streams; CRDT collaboration is deferred).

---

## 4. System Features (Functional Requirements)

### 4.1 Identity, Tenancy, and RBAC

**FR-4.1.1** The system SHALL support local email/password accounts with password hashing via Argon2id.
**FR-4.1.2** The system SHALL support OIDC-based SSO where the operator configures an IdP.
**FR-4.1.3** All tenant-scoped tables SHALL carry a nullable `organization_id` column. In v1 self-host, exactly one organization row exists per install; the column is populated but is not enforced as non-null at the schema level, enabling a future backfill-only migration to multi-tenant.
**FR-4.1.4** The system SHALL implement role-based access control with the following project roles: `project_owner`, `scrum_master`, `developer`, `qa`, `viewer`. Organization-level roles: `org_admin`, `member`.
**FR-4.1.5** Invitations SHALL be supported for both internal users and client stakeholders. An invitation has states `pending`, `accepted`, `revoked`, `expired`. Default expiry: 7 days.
**FR-4.1.6** The system SHALL support user deactivation (soft delete). Deactivated users retain historical attribution but cannot log in or be assigned new work.
**FR-4.1.7** Password reset SHALL be available via email-token; the operator MAY disable email-based reset in air-gapped installs, in which case org admins issue reset links.

### 4.2 Client & Project Management

**FR-4.2.1** The system SHALL model `clients` as a first-class entity above `projects`. A client MAY have zero or many projects.
**FR-4.2.2** Each project SHALL have a stable human-readable `key` (e.g. `ACME-PORTAL`) that prefixes work item sequence numbers.
**FR-4.2.3** Each project SHALL specify a methodology (`agile`, `waterfall`, `hybrid`) at creation. Methodology MAY be changed post-creation with a warning and an audit-log entry, but the change SHALL NOT retroactively rewrite existing work items or state history.
**FR-4.2.4** Each project SHALL carry an `ai_enabled` boolean and a `llm_config` object (typed Pydantic schema) that governs per-project AI behavior.
**FR-4.2.5** Each project SHALL declare a `client_portal_mode` of `none`, `export_only`, or `portal`. Default: `export_only`.
**FR-4.2.6** Each project SHALL carry `start_date`, `target_date`, and `status` (`active`, `on_hold`, `completed`, `cancelled`).

### 4.3 Methodology Configuration

**FR-4.3.1** The system SHALL ship seed methodology templates (Agile, Waterfall, Hybrid) as data in `packages/methodology-templates/` and apply the chosen template on project creation to populate `workflow_states`, `workflow_transitions`, and `hierarchy_rules`.
**FR-4.3.2** Project owners SHALL be able to edit workflow states, transitions, and hierarchy rules post-creation, subject to the constraint that no existing work item may be in a removed state and no existing parent/child pair may violate a removed hierarchy rule.
**FR-4.3.3** The Agile template SHALL define the hierarchy `epic → feature → story → task` and states `backlog → in_progress → in_review → qa → done`, with `bug` allowed as a sibling of `story`.
**FR-4.3.4** The Waterfall template SHALL define the hierarchy `phase → deliverable → task` and states `not_started → in_progress → gate_review → done`, with `gate_review → done` marked `is_hard_gate = TRUE`.
**FR-4.3.5** The Hybrid template SHALL support Waterfall phases wrapping Agile sprints, i.e. a `phase` MAY contain `epic` children and each transition out of `phase.gate_review` is a hard gate.

### 4.4 Work Item Engine

**FR-4.4.1** The system SHALL persist all work items in a single polymorphic `work_items` table discriminated by `kind`.
**FR-4.4.2** Every work item SHALL have a unique per-project sequence number (`seq`) and a human key (`<project.key>-<seq>`).
**FR-4.4.3** The system SHALL enforce hierarchy rules on parent-child assignment. Violations return a 422 with the offending pair.
**FR-4.4.4** The system SHALL enforce state transitions via `workflow_transitions`. Attempts to transition outside allowed edges return 422. Attempts to execute a `is_hard_gate = TRUE` transition without an approved milestone return 409.
**FR-4.4.5** Work items SHALL support `derived_from`, `tests`, `blocks`, and `relates_to` link types via `work_item_links`. Cycles on `derived_from` chains SHALL be rejected by an application-level cycle check.
**FR-4.4.6** Work items SHALL support both `story_points` and `estimated_hours`. When both are set, `estimated_hours` drives capacity math; `story_points` drives velocity reporting.
**FR-4.4.7** The system SHALL support lexorank-based ranking (`rank` column) for backlog and board ordering; rebalancing SHALL be O(1) amortized on a single row.
**FR-4.4.8** Bulk operations (assign, move to sprint, transition) SHALL be supported with per-item authorization and per-item error reporting.
**FR-4.4.9** Every work item change SHALL emit an `audit_log` row.

### 4.5 Document Management

**FR-4.5.1** The system SHALL manage documents of type `srs`, `hld`, `lld`, `test_plan`, and `other`.
**FR-4.5.2** Every save SHALL create a new immutable `document_versions` row with monotonic `version_no`. Prior versions SHALL NOT be mutated.
**FR-4.5.3** Documents SHALL have `status` transitions: `draft → in_review → approved → superseded`. Only one version per document MAY have `status = 'approved'` at any moment; approving a new version SHALL supersede the previous approved one.
**FR-4.5.4** On save, the system SHALL chunk the document by heading hierarchy (H1 through H4) into `document_chunks`, tag each chunk with a `section_path` (e.g. `3.2.1 Authentication`), and enqueue embedding computation.
**FR-4.5.5** Each chunk SHALL persist `embedding vector(768)`, `embedding_model TEXT`, and OPTIONALLY `embedding_alt vector(1536)` with `embedding_alt_model TEXT`. The AI retrieval query selects the chunk column matching the configured retrieval model.
**FR-4.5.6** Only chunks belonging to a `document.current_version_id` where the corresponding version's `status = 'approved'` SHALL participate in AI retrieval by default. An org-level flag MAY allow drafts to participate in author-only retrieval for iterative writing.
**FR-4.5.7** Mermaid.js code blocks SHALL be rendered in-place in the reading view and preserved verbatim in the underlying Markdown.
**FR-4.5.8** Concurrent edits SHALL be reconciled via optimistic locking on `document.current_version_id`. On conflict, the second writer is returned a 409 with the diff to the current head.
**FR-4.5.9** Documents SHALL be exportable to Markdown and PDF. PDF export SHALL preserve section anchors and rendered Mermaid diagrams.

### 4.6 AI Agent Layer

**FR-4.6.1** The system SHALL implement five role agents in v1: Project Owner (PO), Architect, Scrum Master, Developer, QA. Each is a data profile of retrieval policy + system template + output schema + model tier, not code.
**FR-4.6.2** Agent invocation SHALL be gated by (a) `project.ai_enabled`, (b) the invoker's project role permission for the agent, (c) presence of all approved prerequisite documents for the target artifact.
**FR-4.6.3** Every AI generation SHALL be run as an async job persisted in `ai_generation_jobs` with a `job_status` lifecycle: `queued → running → awaiting_review → accepted | rejected | failed`.
**FR-4.6.4** Every AI generation SHALL persist `ai_provenance` rows (chunks and items consumed) BEFORE the LLM call is made. If the LLM call fails, the provenance record is retained for post-mortem.
**FR-4.6.5** Every AI generation output SHALL be persisted as a draft (`document_versions.status = 'draft'` or `work_items.ai_generated = TRUE`) linked to the source job via `source_job_id`.
**FR-4.6.6** No AI-produced content SHALL become canonical without an explicit human acceptance action, which SHALL be audited.
**FR-4.6.7** Agent output SHALL be constrained by Pydantic schemas passed as `response_format` to the LLM through LiteLLM. Fields absent from the schema SHALL NOT be persisted, regardless of what the LLM emits.
**FR-4.6.8** The system SHALL emit a live progress stream for each job via SSE at `GET /projects/{id}/artifacts/jobs/{job_id}/events`, with heartbeat pings every 15 seconds and a terminal event marking success or failure. On worker heartbeat miss (>60s), the job transitions to `failed` with error `worker_heartbeat_missed`.
**FR-4.6.9** The Context Assembler SHALL always include lineage chunks (deterministic CTE traversal of `derived_from`) before filling the remaining token budget with pgvector top-k.
**FR-4.6.10** When an approved SRS version supersedes a prior one, a background job SHALL diff the chunks, walk provenance to find downstream artifacts derived from removed or changed chunks, and flag them as `stale`. The system SHALL NOT auto-regenerate; humans review and re-invoke.
**FR-4.6.11** The AI agent plugin surface SHALL be a Python entry-point group `krititva.agents` so community contributions can register a new profile without forking core.
**FR-4.6.12** Agent invocation SHALL support per-agent kill-switches on `project.llm_config.disabled_agents`, in addition to the whole-project `ai_enabled` flag.

### 4.7 Approval Workflows & Gates

**FR-4.7.1** The system SHALL model milestones as approvable objects with `gate_status` ∈ `pending`, `in_review`, `approved`, `rejected`.
**FR-4.7.2** Each `workflow_transitions` row with `is_hard_gate = TRUE` SHALL declare a quorum specification: the required set of `(role, count)` pairs whose approvals must be recorded on the linked milestone.
**FR-4.7.3** Approvals SHALL be recorded in a `milestone_approvals` table: `(milestone_id, user_id, role_at_approval, decision, reason, decided_at)`. A single user MAY hold at most one decision per milestone at a time; a subsequent decision by the same user replaces the prior with an audit-log entry.
**FR-4.7.4** A milestone becomes `approved` when the quorum specification is fully satisfied by non-rejecting decisions. It becomes `rejected` when any single required role decision is `reject`.
**FR-4.7.5** Client stakeholders MAY be granted co-approver rights per gate when `client_portal_mode = 'portal'`.
**FR-4.7.6** Rejection SHALL carry a mandatory reason field, exposed in the reporting layer for client-visible dispute records.
**FR-4.7.7** Approval decisions SHALL be revocable before the linked transition is executed; revocation is audited.

### 4.8 Sprints & Capacity

**FR-4.8.1** The system SHALL support sprints scoped to a project with `starts_on`, `ends_on`, and `state` ∈ `planned`, `active`, `closed`.
**FR-4.8.2** The system SHALL support `capacity_entries` recording per-user `availability`, `vacation`, and `allocation`, with `sprint_id` and `project_id` as optional scoping.
**FR-4.8.3** A sprint capacity view SHALL compute available hours per assignee as `sum(availability) - sum(vacation) - sum(other-project allocations)` over the sprint date range.
**FR-4.8.4** Overallocation (sum of `estimated_hours` on assigned items > available hours) SHALL be surfaced as a bottleneck flag on the sprint dashboard and to the Scrum Master agent.
**FR-4.8.5** Full velocity modeling, historical trending, and cross-project load balancing are **deferred to v1.5**. v1 exposes only per-sprint aggregates.

### 4.9 Reporting

**FR-4.9.1** The system SHALL provide a `roadmap_vs_milestone` report per project showing planned milestones, actual gate outcomes, dates, and reasons.
**FR-4.9.2** The report SHALL be exportable to PDF and available as a client-facing view when `client_portal_mode` is `export_only` (link-signed PDF) or `portal` (in-app view).
**FR-4.9.3** A team progress view SHALL summarize open items by state, sprint burndown, and current bottleneck flags. Client-facing exposure of the team progress view is off by default.
**FR-4.9.4** Additional reports (velocity trending, individual utilization) are v1.5+.

### 4.10 Audit & Provenance

**FR-4.10.1** The system SHALL persist an append-only `audit_log` for: user auth events, RBAC changes, project config changes, gate approvals/rejections, AI job lifecycle transitions, draft accept/reject, document status changes, and manual `llm_config` edits.
**FR-4.10.2** Every AI generation SHALL be traceable end-to-end: job → chunks/items consumed → model version → output draft → acceptor.
**FR-4.10.3** The audit log SHALL be exportable per-project in JSONL for external SIEM ingestion.
**FR-4.10.4** Document versions and AI generation jobs SHALL be immutable once persisted; corrections are new rows, not mutations.

### 4.11 Client Portal

**FR-4.11.1** When `client_portal_mode = 'export_only'`, the system SHALL generate signed URLs (default TTL: 7 days) to project reports and specific document versions. URLs SHALL be revocable per project.
**FR-4.11.2** When `client_portal_mode = 'portal'`, invited client users SHALL log in via the same auth surface and receive `viewer` role by default, extensible to `client_approver` per gate.
**FR-4.11.3** Client users SHALL NOT see internal work item comments, capacity data, or team availability. The response serializer SHALL enforce this via a `for_audience` flag rather than field-by-field opt-in on the client.
**FR-4.11.4** Every client-portal access (link fetch or in-app view) SHALL be audit-logged with actor identity or (for signed links) the link ID.

### 4.12 Self-Host Operations

**FR-4.12.1** `docker compose up` SHALL bring up: web, api, worker, postgres+pgvector, redis, litellm gateway, and (optionally) langfuse.
**FR-4.12.2** First-run bootstrap SHALL create the singleton `organizations` row, prompt for the initial `org_admin`, and offer a one-click "pull recommended local models" action (network permitting).
**FR-4.12.3** Backups: the system SHALL document a `pg_dump`-based backup procedure and provide an `krititva backup` CLI wrapper that snapshots Postgres and copies uploaded assets.
**FR-4.12.4** Upgrades: migrations SHALL run automatically at api start, gated by an advisory lock so multiple api replicas do not race. Migration failures SHALL halt startup with a clear error.
**FR-4.12.5** Telemetry SHALL be strictly opt-in via `KRITITVA_TELEMETRY_ENABLED=true`; off by default; the running instance SHALL emit exactly zero outbound requests when disabled (excluding user-initiated LLM calls).

---

## 5. Non-Functional Requirements

### 5.1 Performance
- **NFR-5.1.1** API p95 latency for non-AI endpoints SHALL be ≤ 300 ms on the reference server (4 vCPU / 16 GB) at 50 concurrent active users.
- **NFR-5.1.2** Kanban board load for a project with 5,000 open work items SHALL complete initial render in ≤ 1.5 s.
- **NFR-5.1.3** Vector retrieval (top-20 chunks from a 10,000-chunk corpus) SHALL complete in ≤ 150 ms p95 with the HNSW index.
- **NFR-5.1.4** AI generation end-to-end latency is best-effort and model-dependent; the system SHALL surface a live progress stream (§FR-4.6.8) rather than block clients.
- **NFR-5.1.5** Document save (including chunking + embedding enqueue, but excluding the embedding compute itself) SHALL complete in ≤ 500 ms p95 for documents up to 50,000 tokens.

### 5.2 Security
- **NFR-5.2.1** Passwords SHALL be hashed with Argon2id (memory ≥ 64 MiB, iterations ≥ 3, parallelism ≥ 1).
- **NFR-5.2.2** Session tokens SHALL be short-lived JWTs (≤ 30 min) with refresh tokens rotated on use.
- **NFR-5.2.3** All LLM provider keys and IdP client secrets SHALL be encrypted at rest with a KMS-supplied or file-based data-key; the raw values SHALL NEVER be returned by any read API.
- **NFR-5.2.4** All external requests SHALL be TLS-terminated; the app SHALL emit HSTS headers and reject non-TLS traffic on the public interface.
- **NFR-5.2.5** The API SHALL enforce per-organization rate limits, and per-user AI job concurrency limits (default: 3 concurrent per user, configurable).
- **NFR-5.2.6** Prompt-injection posture: document content SHALL be wrapped in delimited blocks with system-template instructions to ignore embedded instructions; LLM outputs SHALL be schema-validated with the rule that unmapped fields are dropped. Fields whose values could execute in the app (URLs, HTML) SHALL be sanitized on both write and render paths.
- **NFR-5.2.7** Embeddings inherit the confidentiality class of their source document; backup and export flows SHALL treat the `embedding` and `embedding_alt` columns with the same controls as `content`.
- **NFR-5.2.8** All API responses SHALL avoid membership disclosure: unauthorized reads return 404, not 403, for resources the caller must not know exist.
- **NFR-5.2.9** The system SHALL implement CSRF protection on all state-changing endpoints for browser sessions.

### 5.3 Reliability & Availability
- **NFR-5.3.1** Worker crashes MID-generation SHALL leave the corresponding job in a recoverable state; a heartbeat-missed sweeper SHALL mark stuck jobs as `failed` within 60 s.
- **NFR-5.3.2** SSE endpoints SHALL emit heartbeats every 15 s and be safe to disconnect and resume via the polling endpoint.
- **NFR-5.3.3** Database migrations SHALL be reversible where technically feasible; irreversible migrations SHALL be flagged in a changelog entry.
- **NFR-5.3.4** The system SHALL NOT lose data on a single-worker crash; all durable state lives in Postgres.

### 5.4 Maintainability & Extensibility
- **NFR-5.4.1** Backend code SHALL be typed with Python 3.12 type hints; CI SHALL enforce `mypy --strict` on the `app/` package.
- **NFR-5.4.2** Frontend code SHALL be TypeScript strict-mode.
- **NFR-5.4.3** Test coverage on the work item engine, gate engine, and Context Assembler SHALL be ≥ 90% line coverage.
- **NFR-5.4.4** Public API changes SHALL be governed by an OpenAPI diff check in CI.
- **NFR-5.4.5** New AI agent roles SHALL be addable via the plugin surface (§FR-4.6.11) without editing core packages.

### 5.5 Portability & Deployability
- **NFR-5.5.1** The compose stack SHALL run on Linux (x86_64 + arm64) and on macOS/Windows Docker Desktop for local development.
- **NFR-5.5.2** No cloud-specific service dependencies; the stack SHALL run in an air-gapped environment with only container images and model weights pre-staged.
- **NFR-5.5.3** State SHALL be limited to Postgres + Redis + a filesystem volume for uploaded assets; a fresh install with restored volumes and dumps SHALL be functionally equivalent to the source.

### 5.6 Compliance & Licensing
- **NFR-5.6.1** Core is AGPL-3.0. Contributions require DCO sign-off or lightweight CLA acceptance.
- **NFR-5.6.2** The install MUST NOT ship LLM weights; models are pulled at first run.
- **NFR-5.6.3** Default embedding model (`nomic-embed-text` v1.5) is Apache-2.0 and compatible with AGPL redistribution of prompts/outputs.
- **NFR-5.6.4** GDPR right-to-erasure: the system SHALL provide a per-user erasure procedure that removes PII fields (email, name) and unbinds all attribution to a stable pseudonym while preserving audit integrity. Document contents and embeddings authored by the user are NOT auto-erased; erasure of those requires the org admin to explicitly select scope.

---

## 6. Other Requirements

### 6.1 Internationalization
- **OR-6.1.1** UI text SHALL be extracted for i18n from day one, even if only English ships in v1.
- **OR-6.1.2** All date/time storage SHALL be UTC; display SHALL respect user timezone preference.

### 6.2 Documentation
- **OR-6.2.1** `README.md`, `CONTRIBUTING.md`, agent plugin guide, and self-host operator guide SHALL be part of the v1 release.
- **OR-6.2.2** OpenAPI spec SHALL be published at `/api/openapi.json` and rendered at `/api/docs`.

### 6.3 Traceability
- **OR-6.3.1** Every FR/NFR in this document SHALL be linked to at least one Epic in the roadmap and at least one Test Case in the QA plan. Traceability enforcement is a CI-time check against a manifest generated from this SRS.

---

## Appendix A. Requirement-to-Work-Item Traceability (seed)

This is the seed mapping consumed by the roadmap generator. Full coverage is validated during phase planning.

| FR / NFR | Roadmap milestone | Owning agent role (for review) |
|---|---|---|
| FR-4.1.* | M0 Foundation | Project Owner |
| FR-4.2.*, FR-4.3.* | M0 Foundation | Project Owner |
| FR-4.4.*, FR-4.7.* | M0 Foundation | Architect |
| FR-4.5.* | M1 Artifact chain MVP | Architect |
| FR-4.6.* | M1 → M2 Full agent suite | Architect + QA |
| FR-4.8.*, FR-4.9.* | M3 Agency layer | Scrum Master |
| FR-4.11.* | M3 Agency layer | Project Owner |
| FR-4.12.*, NFR-5.5.* | M0, M4 | Architect |
| NFR-5.2.* | All milestones (security review gate) | Architect |
| NFR-5.3.* | M1, M2 | Architect |

## Appendix B. Open Items Deferred From This SRS

1. Formal SLO and error-budget policy for the hosted-edition variant (out of scope for OSS core).
2. Time-tracking and billing integration surface — a webhook-only API is proposed for v2 but not specified here.
3. CRDT collaborative editing (v2 candidate).
4. Auto-scheduling Gantt (v2+).
