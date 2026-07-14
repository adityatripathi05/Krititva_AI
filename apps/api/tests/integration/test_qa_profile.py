"""QAProfile tests (M1.T6, FR-4.6.1, FR-4.6.5, FR-4.6.7).

The first work-item-producing profile: persist_draft creates test_case work
items (ai_generated, source_job_id) linked to the focus story via `tests`.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import AssembledContext
from app.ai.llm_client import FakeLLMClient
from app.ai.profiles.base import PROFILE_REGISTRY
from app.ai.profiles.qa import MissingCitations, MissingFocusStory, QAProfile
from app.models import (
    AgentRole,
    AIGenerationJob,
    ArtifactType,
    DocType,
    JobStatus,
    LinkType,
    OrgRole,
    Project,
    WorkItem,
    WorkItemKind,
    WorkItemLink,
)
from app.schemas.artifacts import TestCaseSet
from app.schemas.project import ProjectCreate
from app.schemas.work_item import WorkItemCreate
from app.services.audit import AuditSink
from app.services.project import ProjectService
from app.services.work_items import WorkItemService
from tests.integration._factories import make_org, make_user

pytestmark = pytest.mark.integration

_VALID = {
    "cases": [
        {
            "title": "Login with valid credentials",
            "preconditions_md": "A registered user exists.",
            "steps": ["Open login", "Enter email + password", "Submit"],
            "expected_md": "The user reaches the dashboard.",
            "kind": "functional",
            "srs_citations": ["[SRS §4.2]"],
        },
        {
            "title": "Login with wrong password",
            "preconditions_md": "",
            "steps": ["Enter a wrong password", "Submit"],
            "expected_md": "An error is shown; no session is created.",
            "kind": "negative",
            "srs_citations": ["[SRS §4.2]"],
        },
    ],
}


class Ctx:
    def __init__(self, db: AsyncSession, project: Project, actor_id: uuid.UUID) -> None:
        self.db = db
        self.project = project
        self.actor_id = actor_id


async def _ctx(db: AsyncSession) -> Ctx:
    org = await make_org(db)
    admin = await make_user(db, org, org_role=OrgRole.org_admin)
    await db.flush()
    project = await ProjectService(db, AuditSink(db)).create_project(
        admin,
        ProjectCreate(key="QA", name="QA", methodology="agile"),  # type: ignore[arg-type]
    )
    await db.flush()
    return Ctx(db, project, admin.id)


async def _story(ctx: Ctx) -> WorkItem:
    return await WorkItemService(ctx.db, AuditSink(ctx.db)).create(
        ctx.project, ctx.actor_id, WorkItemCreate(kind=WorkItemKind.story, title="Login story")
    )


async def _job(ctx: Ctx, focus_item_id: uuid.UUID | None) -> AIGenerationJob:
    job = AIGenerationJob(
        project_id=ctx.project.id,
        requested_by=ctx.actor_id,
        agent_role=AgentRole.qa,
        target_artifact=ArtifactType.test_cases,
        focus_item_id=focus_item_id,
        status=JobStatus.running,
    )
    ctx.db.add(job)
    await ctx.db.flush()
    return job


def _assembled() -> AssembledContext:
    return AssembledContext(lineage=[], semantic=[], operational=[], total_tokens=0)


# ---------------------------------------------------------------------------
# Registry + retrieval + render + schema
# ---------------------------------------------------------------------------


def test_registry_resolves_qa_for_test_cases() -> None:
    assert isinstance(PROFILE_REGISTRY.resolve(AgentRole.qa, ArtifactType.test_cases), QAProfile)


async def test_retrieval_policy_targets_srs_and_lld(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    story = await _story(ctx)
    plan = await QAProfile().retrieval_policy(db_session, ctx.project, story)
    assert set(plan.semantic_doc_types) == {DocType.srs, DocType.lld}
    assert plan.include_lineage is True
    assert plan.token_budget == 12000


def test_test_case_requires_citations() -> None:
    bad = {"cases": [{**_VALID["cases"][0], "srs_citations": []}]}
    with pytest.raises(ValidationError):
        TestCaseSet.model_validate(bad)


def test_test_case_set_drops_unknown_fields() -> None:
    obj = TestCaseSet.model_validate({**_VALID, "injected": "x"})
    assert not hasattr(obj, "injected")


# ---------------------------------------------------------------------------
# persist_draft
# ---------------------------------------------------------------------------


async def test_persist_creates_ai_test_cases_linked_to_story(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    story = await _story(ctx)
    job = await _job(ctx, story.id)
    result = await QAProfile().persist_draft(db_session, job, TestCaseSet.model_validate(_VALID))

    assert len(result.work_item_ids) == 2
    for item_id in result.work_item_ids:
        item = await db_session.get(WorkItem, item_id)
        assert item is not None
        assert item.kind is WorkItemKind.test_case
        assert item.ai_generated is True  # §7.5
        assert item.source_job_id == job.id  # §7.6

    # Each test links to the story via a `tests` link.
    links = (
        (
            await db_session.execute(
                select(WorkItemLink).where(
                    WorkItemLink.to_item == story.id, WorkItemLink.link_type == LinkType.tests
                )
            )
        )
        .scalars()
        .all()
    )
    assert {link.from_item for link in links} == set(result.work_item_ids)


async def test_persist_requires_focus_story(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    job = await _job(ctx, None)
    with pytest.raises(MissingFocusStory):
        await QAProfile().persist_draft(db_session, job, TestCaseSet.model_validate(_VALID))


async def test_persist_rejects_whitespace_citations(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    story = await _story(ctx)
    job = await _job(ctx, story.id)
    doc = TestCaseSet.model_validate({"cases": [{**_VALID["cases"][0], "srs_citations": ["  "]}]})
    with pytest.raises(MissingCitations):
        await QAProfile().persist_draft(db_session, job, doc)


async def test_end_to_end_with_fake_llm(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    story = await _story(ctx)
    job = await _job(ctx, story.id)
    profile = QAProfile()
    result = await FakeLLMClient(_VALID).acompletion(
        model="fake",
        messages=[
            {"role": "system", "content": profile.render_system(_assembled())},
            {"role": "user", "content": profile.render_user(_assembled(), None)},
        ],
        response_format=profile.output_schema,
        metadata={},
    )
    persisted = await profile.persist_draft(db_session, job, result.artifact)
    assert len(persisted.work_item_ids) == 2
    assert persisted.document_version_id is None  # work-item profile, no doc version
