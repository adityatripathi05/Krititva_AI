"""Accept/reject of work-item-producing AI jobs (review finding #2; FR-4.6.6, §1.1).

A QA job persists its output as ``ai_generated=TRUE`` work items — the draft state
of a work item. Accept must clear that flag (canonical); reject must discard them.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AgentRole,
    AIGenerationJob,
    ArtifactType,
    JobStatus,
    OrgRole,
    WorkItem,
    WorkItemKind,
)
from app.schemas.project import ProjectCreate
from app.schemas.work_item import WorkItemCreate
from app.services.ai_orchestrator import AIOrchestrator
from app.services.audit import AuditSink
from app.services.project import ProjectService
from app.services.work_items import WorkItemService
from tests.integration._factories import make_org, make_user

pytestmark = pytest.mark.integration


async def _seed(db: AsyncSession) -> tuple[object, uuid.UUID, AIGenerationJob, list[uuid.UUID]]:
    org = await make_org(db)
    admin = await make_user(db, org, org_role=OrgRole.org_admin)
    await db.flush()
    project = await ProjectService(db, AuditSink(db)).create_project(
        admin,  # type: ignore[arg-type]
        ProjectCreate(key="QA", name="QA", methodology="agile"),  # type: ignore[arg-type]
    )
    await db.flush()
    job = AIGenerationJob(
        project_id=project.id,
        requested_by=admin.id,
        agent_role=AgentRole.qa,
        target_artifact=ArtifactType.test_cases,
        status=JobStatus.awaiting_review,
    )
    db.add(job)
    await db.flush()

    wi = WorkItemService(db, AuditSink(db))
    ids = []
    for i in range(2):
        item = await wi.create(
            project,
            admin.id,
            WorkItemCreate(kind=WorkItemKind.test_case, title=f"TC {i}"),
            ai_generated=True,
            source_job_id=job.id,
        )
        ids.append(item.id)
    return project, admin.id, job, ids


async def test_accept_promotes_work_items_to_canonical(db_session: AsyncSession) -> None:
    project, actor_id, job, ids = await _seed(db_session)
    orch = AIOrchestrator(db_session, AuditSink(db_session))
    outcome = await orch.accept(project, job, actor_id)  # type: ignore[arg-type]

    assert job.status is JobStatus.accepted
    assert sorted(outcome.work_item_ids) == sorted(ids)
    for iid in ids:
        item = await db_session.get(WorkItem, iid)
        assert item is not None
        assert item.ai_generated is False  # §1.1 — human accept made it canonical


async def test_reject_discards_work_items(db_session: AsyncSession) -> None:
    project, actor_id, job, ids = await _seed(db_session)
    orch = AIOrchestrator(db_session, AuditSink(db_session))
    await orch.reject(project, job, actor_id, "not good enough")  # type: ignore[arg-type]

    assert job.status is JobStatus.rejected
    for iid in ids:
        assert await db_session.get(WorkItem, iid) is None  # discarded
