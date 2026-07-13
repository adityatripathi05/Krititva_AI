"""Document service — immutable versioning, optimistic locking, approval
(FR-4.5.1-4.5.4, FR-4.5.7-4.5.9, FR-4.10.4).

Documents are project-scoped; org context flows through ``project_id``. Versions
are append-only (§CLAUDE.md §1.3): a correction is a *new* version, never an edit
of ``content_md``. Only ``status`` moves forward along
``draft → in_review → approved → superseded`` and ``approved_at`` is stamped.

Every mutating method audits before the outer commit (§CLAUDE.md §1.5). The
chunk+embed pipeline that ``create_version`` will enqueue lands in M1.T2; until
then a new draft version is simply persisted.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import InvalidDocumentState, NotFound, VersionConflict
from app.models import (
    DocStatus,
    DocType,
    Document,
    DocumentVersion,
    Project,
)
from app.services.audit import AuditSink

_APPROVABLE = frozenset({DocStatus.draft, DocStatus.in_review})


def _content_hash(content_md: str) -> str:
    return hashlib.sha256(content_md.encode("utf-8")).hexdigest()


class DocumentService:
    def __init__(self, db: AsyncSession, audit: AuditSink) -> None:
        self.db = db
        self.audit = audit

    # -----------------------------------------------------------------
    # Reads (404-not-403: a document outside the project is "not found")
    # -----------------------------------------------------------------

    async def get_document(self, project_id: uuid.UUID, document_id: uuid.UUID) -> Document:
        doc = await self.db.get(Document, document_id)
        if doc is None or doc.project_id != project_id:
            raise NotFound("not_found")
        return doc

    async def list_documents(self, project_id: uuid.UUID) -> list[Document]:
        stmt = (
            select(Document).where(Document.project_id == project_id).order_by(Document.created_at)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_versions(self, document: Document) -> list[DocumentVersion]:
        stmt = (
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.version_no)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_version(self, document: Document, version_id: uuid.UUID) -> DocumentVersion:
        version = await self.db.get(DocumentVersion, version_id)
        if version is None or version.document_id != document.id:
            raise NotFound("not_found")
        return version

    async def _head_version(self, document_id: uuid.UUID) -> DocumentVersion | None:
        """The latest version by ``version_no`` — the optimistic-lock head."""
        stmt = (
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_no.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    # -----------------------------------------------------------------
    # Create document (no version yet; current_version_id stays NULL)
    # -----------------------------------------------------------------

    async def create(
        self, project: Project, doc_type: DocType, title: str, actor_id: uuid.UUID
    ) -> Document:
        doc = Document(project_id=project.id, doc_type=doc_type, title=title)
        self.db.add(doc)
        await self.db.flush()
        await self.audit.write(
            action="document.created",
            entity="document",
            entity_id=doc.id,
            actor_id=actor_id,
            organization_id=project.organization_id,
            project_id=project.id,
            detail={"doc_type": doc_type.value, "title": title},
        )
        await self.db.flush()
        return doc

    # -----------------------------------------------------------------
    # Create version (append-only draft; optimistic lock on base_version_id)
    # -----------------------------------------------------------------

    async def create_version(
        self,
        project: Project,
        document: Document,
        actor_id: uuid.UUID,
        content_md: str,
        base_version_id: uuid.UUID | None,
        change_summary: str | None,
        ai_job_id: uuid.UUID | None = None,
    ) -> DocumentVersion:
        head = await self._head_version(document.id)
        self._assert_base_is_head(base_version_id, head)
        version_no = 1 if head is None else head.version_no + 1

        version = DocumentVersion(
            document_id=document.id,
            version_no=version_no,
            content_md=content_md,
            content_hash=_content_hash(content_md),
            status=DocStatus.draft,
            change_summary=change_summary,
            created_by=actor_id,
            ai_job_id=ai_job_id,
        )
        self.db.add(version)
        await self.db.flush()
        await self.audit.write(
            action="document.version.created",
            entity="document_version",
            entity_id=version.id,
            actor_id=actor_id,
            organization_id=project.organization_id,
            project_id=project.id,
            detail={
                "document_id": str(document.id),
                "version_no": version_no,
                "ai_generated": ai_job_id is not None,
            },
        )
        await self.db.flush()
        return version

    @staticmethod
    def _assert_base_is_head(
        base_version_id: uuid.UUID | None, head: DocumentVersion | None
    ) -> None:
        head_id = head.id if head is not None else None
        if base_version_id == head_id:
            return
        detail: dict[str, object] = {}
        if head is not None:
            detail = {"head_version_id": str(head.id), "head_version_no": head.version_no}
        raise VersionConflict(
            "base_version_id does not match the document's current head",
            detail=detail,
        )

    # -----------------------------------------------------------------
    # Approve (single-approved invariant; supersede the prior approved)
    # -----------------------------------------------------------------

    async def approve(
        self, project: Project, document: Document, version_id: uuid.UUID, actor_id: uuid.UUID
    ) -> DocumentVersion:
        version = await self.get_version(document, version_id)
        if version.status not in _APPROVABLE:
            raise InvalidDocumentState(
                "only draft or in_review versions can be approved",
                detail={"status": version.status.value},
            )

        prior = await self._current_approved(document.id)
        if prior is not None and prior.id != version.id:
            prior.status = DocStatus.superseded
            await self.db.flush()

        version.status = DocStatus.approved
        version.approved_at = datetime.now(UTC)
        document.current_version_id = version.id
        await self.audit.write(
            action="document.version.approved",
            entity="document_version",
            entity_id=version.id,
            actor_id=actor_id,
            organization_id=project.organization_id,
            project_id=project.id,
            detail={
                "document_id": str(document.id),
                "version_no": version.version_no,
                "superseded_version_id": str(prior.id) if prior is not None else None,
            },
        )
        await self.db.flush()
        return version

    async def _current_approved(self, document_id: uuid.UUID) -> DocumentVersion | None:
        stmt = select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.status == DocStatus.approved,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()
