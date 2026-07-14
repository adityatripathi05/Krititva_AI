"""Work Item Engine (FR-4.4.1-4.4.9).

Enforces hierarchy rules, the per-project state machine, cycle-safe linking, and
lexorank ordering. Routes own coarse authorization (project membership); this
service owns the domain invariants and per-item transition auth.

Every mutating method audits before the outer commit (§CLAUDE.md §1.5). Work
items are project-scoped, so org context flows through ``project_id``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import (
    CycleDetected,
    GateNotApproved,
    HierarchyViolation,
    InsufficientRole,
    InvalidRank,
    InvalidReference,
    InvalidTransition,
    NotFound,
)
from app.engine import key_between
from app.models import (
    Document,
    DocumentChunk,
    DocumentVersion,
    HierarchyRule,
    LinkType,
    Milestone,
    Project,
    ProjectMember,
    ProjectRole,
    Sprint,
    WorkflowCategory,
    WorkflowState,
    WorkflowTransition,
    WorkItem,
    WorkItemKind,
    WorkItemLink,
)
from app.schemas.work_item import (
    BulkItemResult,
    LineageNode,
    WorkItemCreate,
)
from app.services.audit import AuditSink

_LINEAGE_MAX_DEPTH = 6


class WorkItemService:
    def __init__(self, db: AsyncSession, audit: AuditSink) -> None:
        self.db = db
        self.audit = audit

    # -----------------------------------------------------------------
    # Reads
    # -----------------------------------------------------------------

    async def get(self, project_id: uuid.UUID, item_id: uuid.UUID) -> WorkItem:
        item = await self.db.get(WorkItem, item_id)
        if item is None or item.project_id != project_id:
            raise NotFound("not_found")
        return item

    async def list_for_project(self, project_id: uuid.UUID) -> list[WorkItem]:
        stmt = (
            select(WorkItem)
            .where(WorkItem.project_id == project_id)
            .order_by(WorkItem.rank.nulls_last(), WorkItem.seq)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    # -----------------------------------------------------------------
    # Create (hierarchy + seq + initial state + rank)
    # -----------------------------------------------------------------

    async def create(
        self,
        project: Project,
        actor_id: uuid.UUID,
        payload: WorkItemCreate,
        *,
        ai_generated: bool = False,
        source_job_id: uuid.UUID | None = None,
    ) -> WorkItem:
        if payload.parent_id is not None:
            await self._check_hierarchy(project.id, payload.parent_id, payload.kind)
        await self._validate_refs(
            project.id,
            assignee_id=payload.assignee_id,
            sprint_id=payload.sprint_id,
            milestone_id=payload.milestone_id,
        )

        # Serialize seq/rank allocation per project so concurrent creates don't
        # collide on uq_work_items_project_seq (→ 500) or mint duplicate ranks.
        await self._lock_project_allocation(project.id)
        state_id = await self._initial_state_id(project.id)
        seq = await self._next_seq(project.id)
        rank = await self._append_rank(project.id)

        item = WorkItem(
            project_id=project.id,
            kind=payload.kind,
            parent_id=payload.parent_id,
            seq=seq,
            title=payload.title,
            description_md=payload.description_md,
            acceptance_md=payload.acceptance_md,
            state_id=state_id,
            assignee_id=payload.assignee_id,
            sprint_id=payload.sprint_id,
            milestone_id=payload.milestone_id,
            story_points=payload.story_points,
            estimated_hours=payload.estimated_hours,
            rank=rank,
            created_by=actor_id,
            ai_generated=ai_generated,
            source_job_id=source_job_id,
        )
        self.db.add(item)
        await self.db.flush()
        await self.audit.write(
            action="work_item.created",
            entity="work_item",
            entity_id=item.id,
            actor_id=actor_id,
            organization_id=project.organization_id,
            project_id=project.id,
            detail={"kind": payload.kind.value, "seq": seq, "ai_generated": ai_generated},
        )
        await self.db.flush()
        return item

    async def _check_hierarchy(
        self, project_id: uuid.UUID, parent_id: uuid.UUID, child_kind: WorkItemKind
    ) -> None:
        parent = await self.db.get(WorkItem, parent_id)
        if parent is None or parent.project_id != project_id:
            raise NotFound("not_found")
        rule = await self.db.get(HierarchyRule, (project_id, parent.kind, child_kind))
        if rule is None:
            raise HierarchyViolation(
                "parent/child kind pair not allowed by methodology",
                detail={"parent_kind": parent.kind.value, "child_kind": child_kind.value},
            )

    async def _validate_refs(
        self,
        project_id: uuid.UUID,
        *,
        assignee_id: uuid.UUID | None,
        sprint_id: uuid.UUID | None,
        milestone_id: uuid.UUID | None,
    ) -> None:
        """Pin optional references to this project: an assignee must be a member,
        and any sprint/milestone must belong to the same project (FR-4.1.3 tenant
        scoping). ``None`` values (unset / cleared) are skipped."""
        if assignee_id is not None:
            member = await self.db.get(ProjectMember, (project_id, assignee_id))
            if member is None:
                raise InvalidReference(
                    "assignee is not a member of this project",
                    detail={"assignee_id": str(assignee_id)},
                )
        if sprint_id is not None:
            sprint = await self.db.get(Sprint, sprint_id)
            if sprint is None or sprint.project_id != project_id:
                raise InvalidReference(
                    "sprint does not belong to this project",
                    detail={"sprint_id": str(sprint_id)},
                )
        if milestone_id is not None:
            milestone = await self.db.get(Milestone, milestone_id)
            if milestone is None or milestone.project_id != project_id:
                raise InvalidReference(
                    "milestone does not belong to this project",
                    detail={"milestone_id": str(milestone_id)},
                )

    async def _initial_state_id(self, project_id: uuid.UUID) -> uuid.UUID:
        """First 'todo'-category state by sort_order; else lowest sort_order overall."""
        stmt = (
            select(WorkflowState.id)
            .where(WorkflowState.project_id == project_id)
            .order_by(
                (WorkflowState.category != WorkflowCategory.todo.value),
                WorkflowState.sort_order,
                WorkflowState.key,
            )
            .limit(1)
        )
        state_id = (await self.db.execute(stmt)).scalar_one_or_none()
        if state_id is None:  # pragma: no cover - a seeded project always has states
            raise NotFound("not_found")
        return state_id

    async def _lock_project_allocation(self, project_id: uuid.UUID) -> None:
        """Transaction-scoped advisory lock namespacing seq/rank allocation to a
        project. Released automatically at commit/rollback; concurrent creates
        and reranks in the same project serialize instead of racing the
        read-modify-write of MAX(seq)/MAX(rank)."""
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('krititva-wi-alloc'), hashtext(:pid))"),
            {"pid": str(project_id)},
        )

    async def _next_seq(self, project_id: uuid.UUID) -> int:
        stmt = select(func.coalesce(func.max(WorkItem.seq), 0)).where(
            WorkItem.project_id == project_id
        )
        return int((await self.db.execute(stmt)).scalar_one()) + 1

    async def _append_rank(self, project_id: uuid.UUID) -> str:
        stmt = select(func.max(WorkItem.rank)).where(WorkItem.project_id == project_id)
        current_max = (await self.db.execute(stmt)).scalar_one_or_none()
        return key_between(current_max, None)

    # -----------------------------------------------------------------
    # Field update (non-state edits)
    # -----------------------------------------------------------------

    async def update_fields(
        self,
        project: Project,
        item: WorkItem,
        changes: dict[str, object],
        actor_id: uuid.UUID,
    ) -> WorkItem:
        def _ref(key: str) -> uuid.UUID | None:
            value = changes.get(key)
            return value if isinstance(value, uuid.UUID) else None

        await self._validate_refs(
            project.id,
            assignee_id=_ref("assignee_id"),
            sprint_id=_ref("sprint_id"),
            milestone_id=_ref("milestone_id"),
        )
        for field, value in changes.items():
            setattr(item, field, value)
        await self.audit.write(
            action="work_item.updated",
            entity="work_item",
            entity_id=item.id,
            actor_id=actor_id,
            organization_id=project.organization_id,
            project_id=project.id,
            detail={"fields": sorted(changes)},
        )
        await self.db.flush()
        return item

    # -----------------------------------------------------------------
    # Transition (state machine + role + hard gate)
    # -----------------------------------------------------------------

    async def transition(
        self,
        project: Project,
        item: WorkItem,
        membership: ProjectMember,
        to_state_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> WorkItem:
        edge = await self._find_edge(project.id, item.state_id, to_state_id)
        if edge is None:
            raise InvalidTransition(
                "no transition edge for this state pair",
                detail={"from_state": str(item.state_id), "to_state": str(to_state_id)},
            )
        self._check_transition_role(edge, membership)
        if edge.is_hard_gate:
            # FR-4.4.4: a hard gate needs an approved milestone. The approval
            # (quorum) path lands in M2; until then, no gate can be crossed.
            raise GateNotApproved(
                "hard-gate transition requires an approved milestone",
                detail={"transition_id": str(edge.id)},
            )
        from_state = item.state_id
        item.state_id = to_state_id
        await self.audit.write(
            action="work_item.transitioned",
            entity="work_item",
            entity_id=item.id,
            actor_id=actor_id,
            organization_id=project.organization_id,
            project_id=project.id,
            detail={"from_state": str(from_state), "to_state": str(to_state_id)},
        )
        await self.db.flush()
        return item

    async def _find_edge(
        self, project_id: uuid.UUID, from_state: uuid.UUID, to_state: uuid.UUID
    ) -> WorkflowTransition | None:
        stmt = select(WorkflowTransition).where(
            WorkflowTransition.project_id == project_id,
            WorkflowTransition.from_state == from_state,
            WorkflowTransition.to_state == to_state,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    @staticmethod
    def _check_transition_role(edge: WorkflowTransition, membership: ProjectMember) -> None:
        if edge.required_role is None:
            return
        if membership.role in (edge.required_role, ProjectRole.project_owner):
            return
        raise InsufficientRole(
            f"transition requires role {edge.required_role.value}",
            detail={"required_role": edge.required_role.value},
        )

    # -----------------------------------------------------------------
    # Link (cycle-safe on derived_from)
    # -----------------------------------------------------------------

    async def link(
        self,
        project: Project,
        from_item: WorkItem,
        to_item_id: uuid.UUID | None,
        to_chunk_id: uuid.UUID | None,
        link_type: LinkType,
        actor_id: uuid.UUID,
    ) -> WorkItemLink:
        if to_item_id is not None:
            if to_item_id == from_item.id:
                raise CycleDetected("a work item cannot link to itself")
            target = await self.db.get(WorkItem, to_item_id)
            if target is None or target.project_id != project.id:
                raise NotFound("not_found")
            if link_type is LinkType.derived_from:
                await self._assert_no_derived_cycle(from_item.id, to_item_id)

        if to_chunk_id is not None:
            await self._assert_chunk_in_project(project.id, to_chunk_id)

        row = WorkItemLink(
            from_item=from_item.id,
            to_item=to_item_id,
            to_chunk=to_chunk_id,
            link_type=link_type,
        )
        self.db.add(row)
        await self.db.flush()
        await self.audit.write(
            action="work_item.linked",
            entity="work_item_link",
            entity_id=row.id,
            actor_id=actor_id,
            organization_id=project.organization_id,
            project_id=project.id,
            detail={"from": str(from_item.id), "to": str(to_item_id), "type": link_type.value},
        )
        await self.db.flush()
        return row

    async def _assert_chunk_in_project(self, project_id: uuid.UUID, chunk_id: uuid.UUID) -> None:
        """Scope a ``to_chunk`` link target to this project (FR-4.1.3, NFR-5.2.8).

        Without this, a member of two projects could link a work item to a chunk
        in the *other* project; the lineage retrieval would then pull that
        project's document content into this project's AI context. A foreign or
        nonexistent chunk resolves to 404, mirroring the ``to_item`` path."""
        chunk_project = (
            await self.db.execute(
                select(Document.project_id)
                .join(DocumentVersion, DocumentVersion.document_id == Document.id)
                .join(DocumentChunk, DocumentChunk.version_id == DocumentVersion.id)
                .where(DocumentChunk.id == chunk_id)
            )
        ).scalar_one_or_none()
        if chunk_project is None or chunk_project != project_id:
            raise NotFound("not_found")

    async def _assert_no_derived_cycle(self, from_id: uuid.UUID, to_id: uuid.UUID) -> None:
        """Reject if ``to_id`` already reaches ``from_id`` via derived_from edges."""
        seen: set[uuid.UUID] = set()
        frontier = [to_id]
        while frontier:
            current = frontier.pop()
            if current == from_id:
                raise CycleDetected(
                    "derived_from link would create a cycle",
                    detail={"from": str(from_id), "to": str(to_id)},
                )
            if current in seen:
                continue
            seen.add(current)
            stmt = select(WorkItemLink.to_item).where(
                WorkItemLink.from_item == current,
                WorkItemLink.link_type == LinkType.derived_from,
                WorkItemLink.to_item.is_not(None),
            )
            frontier.extend(
                r for r in (await self.db.execute(stmt)).scalars().all() if r is not None
            )

    # -----------------------------------------------------------------
    # Rerank (lexorank; single-row write)
    # -----------------------------------------------------------------

    async def rerank(
        self,
        project: Project,
        item: WorkItem,
        before_id: uuid.UUID | None,
        after_id: uuid.UUID | None,
        actor_id: uuid.UUID,
    ) -> WorkItem:
        await self._lock_project_allocation(project.id)
        before_rank = await self._neighbor_rank(project.id, before_id)
        after_rank = await self._neighbor_rank(project.id, after_id)
        try:
            item.rank = key_between(before_rank, after_rank)
        except ValueError as exc:
            raise InvalidRank(str(exc)) from exc
        await self.audit.write(
            action="work_item.reranked",
            entity="work_item",
            entity_id=item.id,
            actor_id=actor_id,
            organization_id=project.organization_id,
            project_id=project.id,
            detail={"rank": item.rank},
        )
        await self.db.flush()
        return item

    async def _neighbor_rank(
        self, project_id: uuid.UUID, neighbor_id: uuid.UUID | None
    ) -> str | None:
        if neighbor_id is None:
            return None
        neighbor = await self.db.get(WorkItem, neighbor_id)
        if neighbor is None or neighbor.project_id != project_id:
            raise NotFound("not_found")
        if neighbor.rank is None:
            raise InvalidRank("neighbor has no rank")
        return neighbor.rank

    # -----------------------------------------------------------------
    # Bulk transition (per-item auth + per-item error, not group-atomic)
    # -----------------------------------------------------------------

    async def bulk_transition(
        self,
        project: Project,
        membership: ProjectMember,
        item_ids: list[uuid.UUID],
        to_state_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> list[BulkItemResult]:
        results: list[BulkItemResult] = []
        for item_id in item_ids:
            try:
                async with self.db.begin_nested():
                    item = await self.get(project.id, item_id)
                    await self.transition(project, item, membership, to_state_id, actor_id)
                results.append(BulkItemResult(id=item_id, ok=True))
            except (
                NotFound,
                InvalidTransition,
                InsufficientRole,
                GateNotApproved,
            ) as exc:
                results.append(BulkItemResult(id=item_id, ok=False, error_code=exc.code))
        return results

    # -----------------------------------------------------------------
    # Lineage (app-level derived_from walk; chunk lineage empty until docs)
    # -----------------------------------------------------------------

    async def lineage(
        self, item: WorkItem, max_depth: int = _LINEAGE_MAX_DEPTH
    ) -> list[LineageNode]:
        """Walk ``derived_from`` edges from ``item`` and return the ancestry.

        The SQL ``lineage_chunks`` function (document chunks) lands with the
        document schema in M1; until then lineage covers work items only.
        """
        nodes: list[LineageNode] = []
        seen: set[uuid.UUID] = {item.id}
        frontier: list[tuple[uuid.UUID, int]] = [(item.id, 0)]
        while frontier:
            current_id, depth = frontier.pop(0)
            if depth >= max_depth:
                continue
            stmt = select(WorkItemLink.to_item).where(
                WorkItemLink.from_item == current_id,
                WorkItemLink.link_type == LinkType.derived_from,
                WorkItemLink.to_item.is_not(None),
            )
            for target_id in (await self.db.execute(stmt)).scalars().all():
                if target_id is None or target_id in seen:
                    continue
                seen.add(target_id)
                target = await self.db.get(WorkItem, target_id)
                if target is None:  # pragma: no cover - FK guarantees the target exists
                    continue
                nodes.append(
                    LineageNode(
                        id=target.id,
                        kind=target.kind,
                        seq=target.seq,
                        title=target.title,
                        depth=depth + 1,
                    )
                )
                frontier.append((target_id, depth + 1))
        return nodes
