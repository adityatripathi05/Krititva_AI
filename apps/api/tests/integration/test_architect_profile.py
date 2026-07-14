"""ArchitectProfile tests (M1.T5, FR-4.6.1, FR-4.6.5-4.6.7).

Retrieval policy, prompt render, output-schema roundtrip + citation enforcement,
and draft persistence with Mermaid preserved. LLM is the offline FakeLLMClient.
Lives under integration/ because persist_draft needs the real DB fixtures.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context import AssembledContext, ContextChunk
from app.ai.llm_client import FakeLLMClient
from app.ai.profiles.architect import ArchitectProfile, MissingCitations
from app.ai.profiles.base import PROFILE_REGISTRY, GenericDocumentProfile
from app.models import (
    AgentRole,
    AIGenerationJob,
    ArtifactType,
    DocStatus,
    DocType,
    Document,
    DocumentVersion,
    JobStatus,
    OrgRole,
)
from app.schemas.artifacts import DesignDocument
from tests.integration._factories import make_org, make_project, make_user

pytestmark = pytest.mark.integration

_VALID = {
    "title": "System HLD",
    "scope_summary": "High-level design.",
    "sections": [
        {
            "heading": "Overview",
            "section_path": "1",
            "body_md": "The system has three services.",
            "srs_citations": ["[SRS §4.1]"],
        }
    ],
    "mermaid_diagrams": [{"caption": "Topology", "code": "graph TD; A-->B"}],
}


def _assembled() -> AssembledContext:
    chunk = ContextChunk(
        stage="semantic",
        content="Users authenticate with email + password.",
        token_count=8,
        chunk_id=uuid.uuid4(),
        section_path="4.1",
    )
    return AssembledContext(lineage=[], semantic=[chunk], operational=[], total_tokens=8)


async def _job(db: AsyncSession, artifact: ArtifactType = ArtifactType.hld) -> AIGenerationJob:
    org = await make_org(db)
    admin = await make_user(db, org, org_role=OrgRole.org_admin)
    project = await make_project(db, org)
    await db.flush()
    job = AIGenerationJob(
        project_id=project.id,
        requested_by=admin.id,
        agent_role=AgentRole.architect,
        target_artifact=artifact,
        status=JobStatus.running,
    )
    db.add(job)
    await db.flush()
    return job


async def _document_of(db: AsyncSession, version_id: uuid.UUID | None) -> Document:
    assert version_id is not None
    version = await db.get(DocumentVersion, version_id)
    assert version is not None
    doc = await db.get(Document, version.document_id)
    assert doc is not None
    return doc


# ---------------------------------------------------------------------------
# Registry + retrieval policy + render
# ---------------------------------------------------------------------------


def test_registry_resolves_architect() -> None:
    assert isinstance(
        PROFILE_REGISTRY.resolve(AgentRole.architect, ArtifactType.hld), ArchitectProfile
    )
    assert isinstance(
        PROFILE_REGISTRY.resolve(AgentRole.architect, ArtifactType.lld), ArchitectProfile
    )


def test_registry_falls_back_to_generic_for_plain_doc() -> None:
    prof = PROFILE_REGISTRY.resolve(AgentRole.project_owner, ArtifactType.srs)
    assert isinstance(prof, GenericDocumentProfile)


async def test_retrieval_policy_targets_srs_and_hld(db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    project = await make_project(db_session, org)
    plan = await ArchitectProfile().retrieval_policy(db_session, project, None)
    assert set(plan.semantic_doc_types) == {DocType.srs, DocType.hld}
    assert plan.token_budget == 24000
    assert plan.include_lineage is False


def test_render_wraps_context_and_instructions() -> None:
    profile = ArchitectProfile()
    assembled = _assembled()
    system = profile.render_system(assembled)
    user = profile.render_user(assembled, "Design the auth module.")
    assert "Architect" in system
    assert "citation" in system.lower()
    assert "Design the auth module." in user
    assert "Users authenticate" in user  # context embedded as data


# ---------------------------------------------------------------------------
# Schema + citation enforcement
# ---------------------------------------------------------------------------


def test_design_document_requires_section_citations() -> None:
    bad = {**_VALID, "sections": [{**_VALID["sections"][0], "srs_citations": []}]}
    with pytest.raises(ValidationError):
        DesignDocument.model_validate(bad)


def test_design_document_drops_unknown_fields() -> None:
    doc = DesignDocument.model_validate({**_VALID, "injected": "ignore me"})
    assert not hasattr(doc, "injected")


# ---------------------------------------------------------------------------
# persist_draft
# ---------------------------------------------------------------------------


async def test_persist_draft_writes_draft_with_mermaid(db_session: AsyncSession) -> None:
    job = await _job(db_session, ArtifactType.hld)
    doc = DesignDocument.model_validate(_VALID)
    result = await ArchitectProfile().persist_draft(db_session, job, doc)

    assert result.document_version_id is not None
    version = await db_session.get(DocumentVersion, result.document_version_id)
    assert version is not None
    assert version.status is DocStatus.draft
    assert version.ai_job_id == job.id
    assert "```mermaid" in version.content_md  # Mermaid preserved
    assert "[SRS §4.1]" in version.content_md


async def test_persist_draft_uses_target_artifact_doc_type(db_session: AsyncSession) -> None:
    job = await _job(db_session, ArtifactType.lld)
    doc = DesignDocument.model_validate(_VALID)
    result = await ArchitectProfile().persist_draft(db_session, job, doc)
    document = await _document_of(db_session, result.document_version_id)
    assert document.doc_type is DocType.lld


async def test_persist_draft_rejects_whitespace_citations(db_session: AsyncSession) -> None:
    job = await _job(db_session)
    doc = DesignDocument.model_validate(
        {**_VALID, "sections": [{**_VALID["sections"][0], "srs_citations": ["   "]}]}
    )
    with pytest.raises(MissingCitations):
        await ArchitectProfile().persist_draft(db_session, job, doc)


async def test_end_to_end_with_fake_llm(db_session: AsyncSession) -> None:
    job = await _job(db_session)
    profile = ArchitectProfile()
    assembled = _assembled()
    result = await FakeLLMClient(_VALID).acompletion(
        model="fake",
        messages=[
            {"role": "system", "content": profile.render_system(assembled)},
            {"role": "user", "content": profile.render_user(assembled, None)},
        ],
        response_format=profile.output_schema,
        metadata={},
    )
    persisted = await profile.persist_draft(db_session, job, result.artifact)
    assert persisted.document_version_id is not None
