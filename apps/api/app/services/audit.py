"""Audit sink service (§CLAUDE.md §1.5 — audit in the same transaction).

Every state-changing operation SHALL call ``AuditSink.write`` BEFORE
``db.commit``. The sink adds the row and flushes; the outer commit persists it
atomically with the business change. Do not open a new session for audits.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEntry


class AuditSink:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def write(
        self,
        *,
        action: str,
        entity: str,
        entity_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
        organization_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        detail: dict[str, Any] | None = None,
    ) -> AuditEntry:
        row = AuditEntry(
            organization_id=organization_id,
            project_id=project_id,
            actor_id=actor_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            detail=detail or {},
        )
        self.db.add(row)
        await self.db.flush()
        return row
