"""Project service — creation with atomic methodology seeding + config edits.

Routes own authorization; this service owns persistence and the methodology
invariants. Every write path audits before the outer commit (§CLAUDE.md §1.5).

Methodology is data, not code (§CLAUDE.md §1.8): ``create_project`` seeds
``workflow_states`` / ``workflow_transitions`` / ``hierarchy_rules`` from the
JSON template in one transaction with the project row, so a project never exists
without a complete, consistent workflow.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import (
    ConfigInUse,
    DuplicateKey,
    InvalidWorkflowConfig,
    NotFound,
)
from app.methodology import MethodologyTemplate, load_template
from app.models import (
    HierarchyRule,
    Methodology,
    OrgRole,
    Project,
    ProjectMember,
    ProjectRole,
    User,
    WorkflowState,
    WorkflowTransition,
    WorkItemKind,
)
from app.schemas.project import ProjectCreate
from app.services.audit import AuditSink


class ProjectService:
    def __init__(self, db: AsyncSession, audit: AuditSink) -> None:
        self.db = db
        self.audit = audit

    # -----------------------------------------------------------------
    # Creation
    # -----------------------------------------------------------------

    async def create_project(self, actor: User, body: ProjectCreate) -> Project:
        """Create a project and seed its methodology config atomically.

        The creating ``actor`` is enrolled as ``project_owner`` so they can
        manage the project immediately. Raises ``DuplicateKey`` if the project
        key already exists.
        """
        existing = await self.db.execute(select(Project.id).where(Project.key == body.key))
        if existing.scalar_one_or_none() is not None:
            raise DuplicateKey("project key already in use", detail={"key": body.key})

        project = Project(
            organization_id=actor.organization_id,
            client_id=body.client_id,
            key=body.key,
            name=body.name,
            methodology=body.methodology,
            ai_enabled=body.ai_enabled,
            client_portal_mode=body.client_portal_mode,
            start_date=body.start_date,
            target_date=body.target_date,
        )
        self.db.add(project)
        await self.db.flush()

        template = load_template(body.methodology)
        await self._apply_template(project.id, template)

        self.db.add(
            ProjectMember(
                project_id=project.id,
                user_id=actor.id,
                role=ProjectRole.project_owner,
            )
        )

        await self.audit.write(
            action="project.created",
            entity="project",
            entity_id=project.id,
            actor_id=actor.id,
            organization_id=actor.organization_id,
            project_id=project.id,
            detail={"key": body.key, "methodology": body.methodology.value},
        )
        await self.db.flush()
        return project

    async def _apply_template(self, project_id: uuid.UUID, template: MethodologyTemplate) -> None:
        """Insert states, then transitions (resolving state keys), then hierarchy."""
        key_to_id: dict[str, uuid.UUID] = {}
        for st in template.states:
            state = WorkflowState(
                project_id=project_id,
                key=st.key,
                label=st.label,
                category=st.category.value,
                sort_order=st.sort_order,
            )
            self.db.add(state)
            await self.db.flush()
            key_to_id[st.key] = state.id

        for tr in template.transitions:
            self.db.add(
                WorkflowTransition(
                    project_id=project_id,
                    from_state=key_to_id[tr.from_key],
                    to_state=key_to_id[tr.to_key],
                    is_hard_gate=tr.is_hard_gate,
                    required_role=tr.required_role,
                    approval_quorum=dict(tr.approval_quorum),
                )
            )

        for hr in template.hierarchy:
            self.db.add(
                HierarchyRule(
                    project_id=project_id,
                    parent_kind=hr.parent_kind,
                    child_kind=hr.child_kind,
                )
            )
        await self.db.flush()

    # -----------------------------------------------------------------
    # Reads (object-level 404-not-403 lives in the RBAC dependency)
    # -----------------------------------------------------------------

    async def get_project(self, project_id: uuid.UUID) -> Project:
        project = await self.db.get(Project, project_id)
        if project is None:
            raise NotFound("not_found")
        return project

    async def list_for_user(self, user: User) -> list[Project]:
        """Org admins see every project in their org; everyone else sees the
        projects they are a member of."""
        if user.org_role is OrgRole.org_admin:
            stmt = (
                select(Project)
                .where(Project.organization_id == user.organization_id)
                .order_by(Project.created_at.desc())
            )
        else:
            stmt = (
                select(Project)
                .join(ProjectMember, ProjectMember.project_id == Project.id)
                .where(ProjectMember.user_id == user.id)
                .order_by(Project.created_at.desc())
            )
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_states(self, project_id: uuid.UUID) -> list[WorkflowState]:
        stmt = (
            select(WorkflowState)
            .where(WorkflowState.project_id == project_id)
            .order_by(WorkflowState.sort_order, WorkflowState.key)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_transitions(self, project_id: uuid.UUID) -> list[WorkflowTransition]:
        stmt = select(WorkflowTransition).where(WorkflowTransition.project_id == project_id)
        return list((await self.db.execute(stmt)).scalars().all())

    async def list_hierarchy_rules(self, project_id: uuid.UUID) -> list[HierarchyRule]:
        stmt = select(HierarchyRule).where(HierarchyRule.project_id == project_id)
        return list((await self.db.execute(stmt)).scalars().all())

    # -----------------------------------------------------------------
    # Methodology change (FR-4.2.3)
    # -----------------------------------------------------------------

    async def change_methodology(
        self, actor: User, project: Project, methodology: Methodology, reseed: bool
    ) -> Project:
        """Change a project's methodology. Never rewrites work items or state
        history (FR-4.2.3). ``reseed`` re-applies the template's workflow config,
        subject to the same in-use safety as manual edits."""
        old = project.methodology
        if reseed and methodology is not old:
            await self._reseed_workflow(project.id, methodology)
        project.methodology = methodology
        await self.audit.write(
            action="project.methodology_changed",
            entity="project",
            entity_id=project.id,
            actor_id=actor.id,
            organization_id=project.organization_id,
            project_id=project.id,
            detail={"from": old.value, "to": methodology.value, "reseed": reseed},
        )
        await self.db.flush()
        return project

    async def _reseed_workflow(self, project_id: uuid.UUID, methodology: Methodology) -> None:
        kinds_in_use = await self._work_item_kinds_in_use(project_id)
        if kinds_in_use:
            raise ConfigInUse(
                "cannot reseed workflow while work items exist",
                detail={"kinds_in_use": sorted(k.value for k in kinds_in_use)},
            )
        await self.db.execute(
            delete(WorkflowTransition).where(WorkflowTransition.project_id == project_id)
        )
        await self.db.execute(delete(HierarchyRule).where(HierarchyRule.project_id == project_id))
        await self.db.execute(delete(WorkflowState).where(WorkflowState.project_id == project_id))
        await self.db.flush()
        await self._apply_template(project_id, load_template(methodology))

    # -----------------------------------------------------------------
    # Config edits (FR-4.3.2) — with in-use safety checks
    # -----------------------------------------------------------------

    async def update_transition(
        self,
        actor: User,
        project: Project,
        transition_id: uuid.UUID,
        *,
        is_hard_gate: bool | None,
        required_role: ProjectRole | None,
        approval_quorum: dict[str, int] | None,
        fields_set: set[str],
    ) -> WorkflowTransition:
        tr = await self.db.get(WorkflowTransition, transition_id)
        if tr is None or tr.project_id != project.id:
            raise NotFound("not_found")

        if "is_hard_gate" in fields_set and is_hard_gate is not None:
            tr.is_hard_gate = is_hard_gate
        if "required_role" in fields_set:
            tr.required_role = required_role
        if "approval_quorum" in fields_set and approval_quorum is not None:
            tr.approval_quorum = dict(approval_quorum)

        if tr.is_hard_gate and not tr.approval_quorum:
            raise InvalidWorkflowConfig(
                "a hard-gate transition requires a non-empty approval_quorum"
            )
        for role in tr.approval_quorum:
            if role not in ProjectRole.__members__:
                raise InvalidWorkflowConfig(f"approval_quorum names unknown role '{role}'")

        await self.audit.write(
            action="workflow.transition_updated",
            entity="workflow_transition",
            entity_id=tr.id,
            actor_id=actor.id,
            organization_id=project.organization_id,
            project_id=project.id,
            detail={
                "is_hard_gate": tr.is_hard_gate,
                "required_role": tr.required_role.value if tr.required_role else None,
                "approval_quorum": tr.approval_quorum,
            },
        )
        await self.db.flush()
        return tr

    async def replace_hierarchy_rules(
        self,
        actor: User,
        project: Project,
        rules: list[tuple[WorkItemKind, WorkItemKind]],
    ) -> list[HierarchyRule]:
        """Replace-all hierarchy rules (LLD §4.3). Rejects the change if it would
        orphan an existing parent/child pair already used by work items (FR-4.3.2)."""
        new_pairs = set(rules)
        if len(new_pairs) != len(rules):
            raise InvalidWorkflowConfig("duplicate hierarchy rule in payload")

        in_use = await self._parent_child_pairs_in_use(project.id)
        removed_but_used = in_use - new_pairs
        if removed_but_used:
            raise ConfigInUse(
                "cannot remove hierarchy rules that existing work items rely on",
                detail={
                    "violations": [
                        {"parent_kind": p.value, "child_kind": c.value}
                        for p, c in sorted(removed_but_used, key=lambda x: (x[0].value, x[1].value))
                    ]
                },
            )

        await self.db.execute(delete(HierarchyRule).where(HierarchyRule.project_id == project.id))
        await self.db.flush()
        for parent_kind, child_kind in rules:
            self.db.add(
                HierarchyRule(
                    project_id=project.id,
                    parent_kind=parent_kind,
                    child_kind=child_kind,
                )
            )
        await self.audit.write(
            action="workflow.hierarchy_replaced",
            entity="project",
            entity_id=project.id,
            actor_id=actor.id,
            organization_id=project.organization_id,
            project_id=project.id,
            detail={"rule_count": len(rules)},
        )
        await self.db.flush()
        return await self.list_hierarchy_rules(project.id)

    # -----------------------------------------------------------------
    # In-use inspectors — the safety-check seam for M0.T5 work items
    # -----------------------------------------------------------------

    async def _work_item_kinds_in_use(self, project_id: uuid.UUID) -> set[WorkItemKind]:
        """Kinds referenced by existing work items. Empty until work_items lands
        (M0.T5); this is the seam the in-use safety checks hang on (FR-4.3.2)."""
        return set()

    async def _parent_child_pairs_in_use(
        self, project_id: uuid.UUID
    ) -> set[tuple[WorkItemKind, WorkItemKind]]:
        """Parent/child kind pairs realized by existing work-item trees. Empty
        until work_items lands (M0.T5) — see ``_work_item_kinds_in_use``."""
        return set()
