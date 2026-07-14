"""QA agent — generates test cases as work items (M1.T6, FR-4.6.1, FR-4.6.5).

The first work-item-producing profile. It retrieves the approved SRS and LLD,
prompts a mid-tier model for a :class:`TestCaseSet`, and persists each case as a
``test_case`` work item (``ai_generated=TRUE``, ``source_job_id`` set, project's
initial state) linked to the story via a ``tests`` link. Nothing is approved —
the AI-generated items sit in the initial state until a human accepts (§1.1).

The link target is the job's **focus item** (the story under test), never an
LLM-emitted id (§1.10): no field the model returns drives which story the tests
attach to.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import AssembledContext, RetrievalPlan
from app.ai.profiles.base import PersistResult
from app.ai.templating import render_template
from app.models import AIGenerationJob, LinkType, Project, WorkItem, WorkItemKind
from app.models.enums import AgentRole, ArtifactType, DocType
from app.schemas.artifacts import TestCase, TestCaseSet
from app.schemas.work_item import WorkItemCreate
from app.services.audit import AuditSink
from app.services.work_items import WorkItemService

_TOKEN_BUDGET = 12000
_TITLE_MAX = 140


class MissingFocusStory(RuntimeError):
    """test_cases generation needs a focus story to attach the tests to."""


class MissingCitations(RuntimeError):
    """A generated test case carried no citation (§7.4/T6.3)."""


class QAProfile:
    role = AgentRole.qa
    artifacts = frozenset({ArtifactType.test_cases})
    model_tier = "mid"
    output_schema: type[BaseModel] = TestCaseSet

    async def retrieval_policy(
        self, db: AsyncSession, project: Project, focus_item: WorkItem | None
    ) -> RetrievalPlan:
        return RetrievalPlan(
            include_lineage=focus_item is not None,
            semantic_doc_types=[DocType.srs, DocType.lld],
            semantic_k=20,
            token_budget=_TOKEN_BUDGET,
        )

    def render_system(self, assembled: AssembledContext) -> str:
        return render_template("qa_system.j2")

    def render_user(self, assembled: AssembledContext, instructions: str | None) -> str:
        return render_template("qa_user.j2", instructions=instructions, context=assembled.render())

    async def persist_draft(
        self, db: AsyncSession, job: AIGenerationJob, artifact: BaseModel
    ) -> PersistResult:
        assert isinstance(artifact, TestCaseSet)
        _validate_citations(artifact)
        if job.focus_item_id is None:
            raise MissingFocusStory("test_cases generation requires a focus story")
        project = await db.get(Project, job.project_id)
        assert project is not None

        items = WorkItemService(db, AuditSink(db))
        story = await items.get(project.id, job.focus_item_id)  # 404 if not in project
        created: list[uuid.UUID] = []
        for case in artifact.cases:
            payload = WorkItemCreate(
                kind=WorkItemKind.test_case,
                title=case.title[:_TITLE_MAX],
                description_md=_render_case(case),
            )
            item = await items.create(
                project, job.requested_by, payload, ai_generated=True, source_job_id=job.id
            )
            await items.link(project, item, story.id, None, LinkType.tests, job.requested_by)
            created.append(item.id)
        return PersistResult(work_item_ids=created)


def _validate_citations(test_set: TestCaseSet) -> None:
    for case in test_set.cases:
        if not any(c.strip() for c in case.srs_citations):
            raise MissingCitations(f"test case '{case.title}' has no citation")


def _render_case(case: TestCase) -> str:
    lines = [f"**Kind:** {case.kind}", ""]
    if case.preconditions_md.strip():
        lines += ["**Preconditions:**", case.preconditions_md, ""]
    lines.append("**Steps:**")
    lines += [f"{i}. {step}" for i, step in enumerate(case.steps, start=1)]
    lines += ["", "**Expected:**", case.expected_md, ""]
    lines.append("_Citations: " + ", ".join(case.srs_citations) + "_")
    return "\n".join(lines)
