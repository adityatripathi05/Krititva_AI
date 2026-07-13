"""AI artifact HTTP surface (M1.T3, FR-4.6.*).

Drives the real app: enqueue (202), job status, accept/reject RBAC + state,
provenance, and the SSE state-replay frame. The worker isn't run here (no queue
under ASGI transport); jobs are advanced to awaiting_review via the shared
session so the review endpoints can be exercised.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import FakeEmbeddingClient
from app.ai.llm_client import FakeLLMClient
from app.models import (
    AgentRole,
    AIGenerationJob,
    ArtifactType,
    JobStatus,
    Organization,
    OrgRole,
    Project,
    ProjectRole,
    User,
)
from app.schemas.artifacts import GenerateArtifactRequest
from app.security.jwt import encode_access_token
from app.services.ai_orchestrator import AIOrchestrator
from app.services.audit import AuditSink
from app.workers.generation import assemble_context, generate_draft
from tests.integration._factories import make_member, make_org, make_user

pytestmark = pytest.mark.integration


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user.id)}"}


class Seed:
    def __init__(self, admin: User, org_id: uuid.UUID, project_id: uuid.UUID) -> None:
        self.admin = admin
        self.org_id = org_id
        self.project_id = project_id


async def _seed(client: AsyncClient, db: AsyncSession, key: str = "AI") -> Seed:
    org = await make_org(db)
    admin = await make_user(db, org, org_role=OrgRole.org_admin)
    await db.commit()
    proj = (
        await client.post(
            "/api/v1/projects",
            headers=_bearer(admin),
            json={"key": key, "name": key, "methodology": "agile"},
        )
    ).json()
    return Seed(admin, org.id, uuid.UUID(proj["id"]))


async def _add_member(
    db: AsyncSession, project_id: uuid.UUID, org_id: uuid.UUID, role: ProjectRole
) -> User:
    project = await db.get(Project, project_id)
    org_obj = await db.get(Organization, org_id)
    assert project is not None and org_obj is not None
    user = await make_user(db, org_obj)
    await make_member(db, project, user, role)
    await db.commit()
    return user


async def _enqueue(client: AsyncClient, seed: Seed, user: User, **body: object) -> object:
    return await client.post(
        f"/api/v1/projects/{seed.project_id}/artifacts",
        headers=_bearer(user),
        json=body,
    )


async def _seed_awaiting_job(db: AsyncSession, seed: Seed) -> AIGenerationJob:
    """Create a job, run its generation core, and park it at awaiting_review."""
    project = await db.get(Project, seed.project_id)
    assert project is not None
    orch = AIOrchestrator(db, AuditSink(db))
    from app.models import ProjectMember

    membership = await db.get(ProjectMember, (seed.project_id, seed.admin.id))
    assert membership is not None
    job = await orch.enqueue(
        project,
        seed.admin.id,
        membership,
        GenerateArtifactRequest(
            agent_role=AgentRole.project_owner, target_artifact=ArtifactType.srs
        ),
        _Null(),
    )
    assembled = await assemble_context(db, job, FakeEmbeddingClient())
    await generate_draft(db, job, assembled, FakeLLMClient())
    job.status = JobStatus.awaiting_review
    await db.commit()
    return job


class _Null:
    async def try_acquire(self, user_id: uuid.UUID) -> bool:
        return True

    async def release(self, user_id: uuid.UUID) -> None:
        return None


# ---------------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------------


async def test_enqueue_returns_202(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    r = await _enqueue(client, seed, seed.admin, agent_role="project_owner", target_artifact="srs")
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "queued"
    got = await client.get(
        f"/api/v1/projects/{seed.project_id}/artifacts/jobs/{body['job_id']}",
        headers=_bearer(seed.admin),
    )
    assert got.json()["status"] == "queued"


async def test_enqueue_role_artifact_mismatch(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    seed = await _seed(client, db_session)
    r = await _enqueue(client, seed, seed.admin, agent_role="architect", target_artifact="srs")
    assert r.status_code == 422
    assert r.json()["code"] == "role_artifact_mismatch"


async def test_enqueue_prereq_missing_409(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    r = await _enqueue(client, seed, seed.admin, agent_role="architect", target_artifact="hld")
    assert r.status_code == 409
    assert r.json()["code"] == "prereq_missing"


async def test_viewer_cannot_invoke_agent(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    viewer = await _add_member(db_session, seed.project_id, seed.org_id, ProjectRole.viewer)
    r = await _enqueue(client, seed, viewer, agent_role="project_owner", target_artifact="srs")
    assert r.status_code == 403
    assert r.json()["code"] == "insufficient_role"


async def test_non_member_gets_404(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    org = await db_session.get(Organization, seed.org_id)
    assert org is not None
    outsider = await make_user(db_session, org)
    await db_session.commit()
    r = await _enqueue(client, seed, outsider, agent_role="project_owner", target_artifact="srs")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Accept / reject
# ---------------------------------------------------------------------------


async def test_accept_flow(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    job = await _seed_awaiting_job(db_session, seed)
    r = await client.post(
        f"/api/v1/projects/{seed.project_id}/artifacts/jobs/{job.id}/accept",
        headers=_bearer(seed.admin),
    )
    assert r.status_code == 200, r.text
    assert r.json()["document_version_id"] == str(job.result_document_version)


async def test_reject_flow(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    job = await _seed_awaiting_job(db_session, seed)
    r = await client.post(
        f"/api/v1/projects/{seed.project_id}/artifacts/jobs/{job.id}/reject",
        headers=_bearer(seed.admin),
        json={"reason": "needs work"},
    )
    assert r.status_code == 204


async def test_reject_requires_reason(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    job = await _seed_awaiting_job(db_session, seed)
    r = await client.post(
        f"/api/v1/projects/{seed.project_id}/artifacts/jobs/{job.id}/reject",
        headers=_bearer(seed.admin),
        json={"reason": ""},
    )
    assert r.status_code == 422  # pydantic min_length


async def test_developer_cannot_accept(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    dev = await _add_member(db_session, seed.project_id, seed.org_id, ProjectRole.developer)
    job = await _seed_awaiting_job(db_session, seed)
    r = await client.post(
        f"/api/v1/projects/{seed.project_id}/artifacts/jobs/{job.id}/accept",
        headers=_bearer(dev),
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Provenance + SSE
# ---------------------------------------------------------------------------


async def test_provenance_empty_in_m1t3(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    job = await _seed_awaiting_job(db_session, seed)
    r = await client.get(
        f"/api/v1/projects/{seed.project_id}/artifacts/jobs/{job.id}/provenance",
        headers=_bearer(seed.admin),
    )
    assert r.status_code == 200
    assert r.json() == []


async def test_events_stream_replays_state(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    r = await _enqueue(client, seed, seed.admin, agent_role="project_owner", target_artifact="srs")
    job_id = r.json()["job_id"]
    events = await client.get(
        f"/api/v1/projects/{seed.project_id}/artifacts/jobs/{job_id}/events",
        headers=_bearer(seed.admin),
    )
    assert events.status_code == 200
    assert events.headers["content-type"].startswith("text/event-stream")
    assert "event: state" in events.text
