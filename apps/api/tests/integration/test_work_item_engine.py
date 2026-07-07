"""Direct WorkItemService tests — the state-machine + hierarchy decision logic.

These call the service against a real Postgres session (no HTTP layer), which is
the reliable vehicle for the 100%-branch-coverage requirement on the engine
(M0.T5.8, §NFR-5.4.3): coverage.py does not trace coroutines executed through the
httpx ASGI transport, so the HTTP-level tests in ``test_work_items.py`` prove the
wiring while these prove — and measure — the branches.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import (
    CycleDetected,
    GateNotApproved,
    HierarchyViolation,
    InsufficientRole,
    InvalidRank,
    InvalidTransition,
    NotFound,
)
from app.models import (
    LinkType,
    OrgRole,
    Project,
    ProjectMember,
    ProjectRole,
    WorkflowState,
    WorkItemKind,
)
from app.schemas.project import ProjectCreate
from app.schemas.work_item import WorkItemCreate
from app.services.audit import AuditSink
from app.services.project import ProjectService
from app.services.work_items import WorkItemService
from tests.integration._factories import make_member, make_org, make_user

pytestmark = pytest.mark.integration


class Ctx:
    def __init__(
        self,
        svc: WorkItemService,
        project: Project,
        admin_id: uuid.UUID,
        owner_membership: ProjectMember,
        states: dict[str, uuid.UUID],
    ) -> None:
        self.svc = svc
        self.project = project
        self.admin_id = admin_id
        self.owner = owner_membership
        self.states = states


async def _ctx(db: AsyncSession, methodology: str = "agile", key: str = "ENG") -> Ctx:
    org = await make_org(db)
    admin = await make_user(db, org, org_role=OrgRole.org_admin)
    await db.flush()
    proj_svc = ProjectService(db, AuditSink(db))
    project = await proj_svc.create_project(
        admin,
        ProjectCreate(key=key, name=key, methodology=methodology),  # type: ignore[arg-type]
    )
    await db.flush()
    states = {
        s.key: s.id
        for s in (
            await db.execute(select(WorkflowState).where(WorkflowState.project_id == project.id))
        )
        .scalars()
        .all()
    }
    owner = (
        await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project.id, ProjectMember.user_id == admin.id
            )
        )
    ).scalar_one()
    return Ctx(WorkItemService(db, AuditSink(db)), project, admin.id, owner, states)


async def _new(ctx: Ctx, kind: str, title: str, parent_id: uuid.UUID | None = None):
    return await ctx.svc.create(
        ctx.project,
        ctx.admin_id,
        WorkItemCreate(kind=WorkItemKind(kind), title=title, parent_id=parent_id),
    )


# ---- create + hierarchy ---------------------------------------------------


async def test_create_defaults(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    item = await _new(ctx, "epic", "E")
    assert item.seq == 1
    assert item.state_id == ctx.states["backlog"]
    assert item.rank is not None
    assert item.ai_generated is False


async def test_hierarchy_allowed(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    epic = await _new(ctx, "epic", "E")
    feat = await _new(ctx, "feature", "F", parent_id=epic.id)
    assert feat.parent_id == epic.id


async def test_hierarchy_violation(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    epic = await _new(ctx, "epic", "E")
    with pytest.raises(HierarchyViolation) as exc:
        await _new(ctx, "task", "T", parent_id=epic.id)
    assert exc.value.detail == {"parent_kind": "epic", "child_kind": "task"}


async def test_hierarchy_missing_parent(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    with pytest.raises(NotFound):
        await _new(ctx, "feature", "F", parent_id=uuid.uuid4())


# ---- transition state machine (all branches) ------------------------------


async def _drive(ctx: Ctx, item, *keys: str) -> None:
    for k in keys:
        await ctx.svc.transition(ctx.project, item, ctx.owner, ctx.states[k], ctx.admin_id)


async def test_transition_valid(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    item = await _new(ctx, "story", "S")
    await ctx.svc.transition(ctx.project, item, ctx.owner, ctx.states["in_progress"], ctx.admin_id)
    assert item.state_id == ctx.states["in_progress"]


async def test_transition_no_edge(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    item = await _new(ctx, "story", "S")
    with pytest.raises(InvalidTransition):
        await ctx.svc.transition(ctx.project, item, ctx.owner, ctx.states["done"], ctx.admin_id)


async def test_transition_required_role_none(db_session: AsyncSession) -> None:
    """backlog->in_progress has no required_role — the None branch."""
    ctx = await _ctx(db_session)
    item = await _new(ctx, "story", "S")
    await _drive(ctx, item, "in_progress")
    assert item.state_id == ctx.states["in_progress"]


async def test_transition_owner_override(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    item = await _new(ctx, "story", "S")
    await _drive(ctx, item, "in_progress", "in_review", "qa", "done")  # qa->done needs 'qa'
    assert item.state_id == ctx.states["done"]


async def test_transition_role_match(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    qa_user = await make_user(db_session, await _org_of(db_session, ctx))
    qa_member = await make_member(db_session, ctx.project, qa_user, ProjectRole.qa)
    item = await _new(ctx, "story", "S")
    await _drive(ctx, item, "in_progress", "in_review", "qa")
    await ctx.svc.transition(ctx.project, item, qa_member, ctx.states["done"], qa_user.id)
    assert item.state_id == ctx.states["done"]


async def test_transition_role_denied(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    dev_user = await make_user(db_session, await _org_of(db_session, ctx))
    dev_member = await make_member(db_session, ctx.project, dev_user, ProjectRole.developer)
    item = await _new(ctx, "story", "S")
    await _drive(ctx, item, "in_progress", "in_review", "qa")
    with pytest.raises(InsufficientRole):
        await ctx.svc.transition(ctx.project, item, dev_member, ctx.states["done"], dev_user.id)


async def test_transition_hard_gate(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session, methodology="waterfall", key="WFE")
    item = await _new(ctx, "deliverable", "D")
    await _drive(ctx, item, "in_progress", "gate_review")
    with pytest.raises(GateNotApproved):
        await ctx.svc.transition(ctx.project, item, ctx.owner, ctx.states["done"], ctx.admin_id)


# ---- links + cycle --------------------------------------------------------


async def test_link_derived_and_lineage(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    a = await _new(ctx, "story", "A")
    b = await _new(ctx, "task", "B")
    await ctx.svc.link(ctx.project, b, a.id, None, LinkType.derived_from, ctx.admin_id)
    nodes = await ctx.svc.lineage(b)
    assert [n.id for n in nodes] == [a.id]
    assert await ctx.svc.lineage(a) == []


async def test_link_self_cycle(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    a = await _new(ctx, "story", "A")
    with pytest.raises(CycleDetected):
        await ctx.svc.link(ctx.project, a, a.id, None, LinkType.derived_from, ctx.admin_id)


async def test_link_transitive_cycle(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    a = await _new(ctx, "story", "A")
    b = await _new(ctx, "story", "B")
    c = await _new(ctx, "story", "C")
    await ctx.svc.link(ctx.project, a, b.id, None, LinkType.derived_from, ctx.admin_id)
    await ctx.svc.link(ctx.project, b, c.id, None, LinkType.derived_from, ctx.admin_id)
    with pytest.raises(CycleDetected):
        await ctx.svc.link(ctx.project, c, a.id, None, LinkType.derived_from, ctx.admin_id)


async def test_link_non_derived_allows_back_reference(db_session: AsyncSession) -> None:
    """'relates_to' is not cycle-checked — the derived_from-only branch."""
    ctx = await _ctx(db_session)
    a = await _new(ctx, "story", "A")
    b = await _new(ctx, "story", "B")
    await ctx.svc.link(ctx.project, a, b.id, None, LinkType.relates_to, ctx.admin_id)
    link = await ctx.svc.link(ctx.project, b, a.id, None, LinkType.relates_to, ctx.admin_id)
    assert link.link_type is LinkType.relates_to


async def test_link_target_missing(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    a = await _new(ctx, "story", "A")
    with pytest.raises(NotFound):
        await ctx.svc.link(ctx.project, a, uuid.uuid4(), None, LinkType.blocks, ctx.admin_id)


async def test_link_to_chunk_skips_cycle_check(db_session: AsyncSession) -> None:
    """to_chunk target (no to_item) — the ``to_item_id is None`` branch."""
    ctx = await _ctx(db_session)
    a = await _new(ctx, "story", "A")
    link = await ctx.svc.link(
        ctx.project, a, None, uuid.uuid4(), LinkType.derived_from, ctx.admin_id
    )
    assert link.to_chunk is not None


# ---- rerank ---------------------------------------------------------------


async def test_rerank_between(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    a = await _new(ctx, "story", "A")
    b = await _new(ctx, "story", "B")
    c = await _new(ctx, "story", "C")
    await ctx.svc.rerank(ctx.project, c, a.id, b.id, ctx.admin_id)
    assert a.rank is not None and b.rank is not None and c.rank is not None
    assert a.rank < c.rank < b.rank


async def test_rerank_open_ends(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    a = await _new(ctx, "story", "A")
    b = await _new(ctx, "story", "B")
    # Move b before everything (before=None), then after everything (after=None).
    await ctx.svc.rerank(ctx.project, b, None, a.id, ctx.admin_id)
    assert b.rank is not None and a.rank is not None and b.rank < a.rank
    await ctx.svc.rerank(ctx.project, b, a.id, None, ctx.admin_id)
    assert b.rank > a.rank


async def test_rerank_reversed_neighbors(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    a = await _new(ctx, "story", "A")
    b = await _new(ctx, "story", "B")
    c = await _new(ctx, "story", "C")
    with pytest.raises(InvalidRank):
        await ctx.svc.rerank(ctx.project, c, b.id, a.id, ctx.admin_id)  # b > a


async def test_rerank_neighbor_missing(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    a = await _new(ctx, "story", "A")
    with pytest.raises(NotFound):
        await ctx.svc.rerank(ctx.project, a, uuid.uuid4(), None, ctx.admin_id)


# ---- update + bulk --------------------------------------------------------


async def test_update_fields(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    a = await _new(ctx, "story", "A")
    await ctx.svc.update_fields(ctx.project, a, {"title": "renamed"}, ctx.admin_id)
    assert a.title == "renamed"


async def test_bulk_transition_mixed(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    a = await _new(ctx, "story", "A")
    b = await _new(ctx, "story", "B")
    await _drive(ctx, b, "in_progress")  # b no longer in backlog
    results = await ctx.svc.bulk_transition(
        ctx.project, ctx.owner, [a.id, b.id, uuid.uuid4()], ctx.states["in_progress"], ctx.admin_id
    )
    by_id = {r.id: r for r in results}
    assert by_id[a.id].ok is True
    assert by_id[b.id].ok is False and by_id[b.id].error_code == "invalid_transition"
    missing = next(r for r in results if r.id not in (a.id, b.id))
    assert missing.ok is False and missing.error_code == "not_found"


async def test_get_wrong_project_404(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    with pytest.raises(NotFound):
        await ctx.svc.get(uuid.uuid4(), uuid.uuid4())


async def test_list_for_project_ordered(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    await _new(ctx, "story", "A")
    await _new(ctx, "story", "B")
    items = await ctx.svc.list_for_project(ctx.project.id)
    assert [i.title for i in items] == ["A", "B"]


async def test_cycle_walk_dedupes_diamond(db_session: AsyncSession) -> None:
    """A diamond in the derived_from graph is visited once (dedup branch); a new
    link into the diamond that introduces no cycle still succeeds."""
    ctx = await _ctx(db_session)
    d = await _new(ctx, "story", "D")
    b = await _new(ctx, "story", "B")
    c = await _new(ctx, "story", "C")
    a = await _new(ctx, "story", "A")
    link = ctx.svc.link
    await link(ctx.project, b, d.id, None, LinkType.derived_from, ctx.admin_id)
    await link(ctx.project, c, d.id, None, LinkType.derived_from, ctx.admin_id)
    await link(ctx.project, a, b.id, None, LinkType.derived_from, ctx.admin_id)
    await link(ctx.project, a, c.id, None, LinkType.derived_from, ctx.admin_id)
    n = await _new(ctx, "story", "N")
    created = await link(ctx.project, n, a.id, None, LinkType.derived_from, ctx.admin_id)
    assert created.to_item == a.id


async def test_rerank_neighbor_without_rank(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    a = await _new(ctx, "story", "A")
    b = await _new(ctx, "story", "B")
    a.rank = None
    await db_session.flush()
    with pytest.raises(InvalidRank):
        await ctx.svc.rerank(ctx.project, b, a.id, None, ctx.admin_id)


async def test_lineage_respects_max_depth_and_diamond(db_session: AsyncSession) -> None:
    ctx = await _ctx(db_session)
    n = await _new(ctx, "story", "N")
    a = await _new(ctx, "story", "A")
    b = await _new(ctx, "story", "B")
    shared = await _new(ctx, "story", "Shared")
    link = ctx.svc.link
    await link(ctx.project, n, a.id, None, LinkType.derived_from, ctx.admin_id)
    await link(ctx.project, n, b.id, None, LinkType.derived_from, ctx.admin_id)
    await link(ctx.project, a, shared.id, None, LinkType.derived_from, ctx.admin_id)
    await link(ctx.project, b, shared.id, None, LinkType.derived_from, ctx.admin_id)
    # Diamond: `shared` reachable via both a and b but appears once (seen-skip).
    full = await ctx.svc.lineage(n)
    assert sorted(node.id for node in full) == sorted({a.id, b.id, shared.id})
    # max_depth=1 stops before the shared node (depth-limit branch).
    shallow = await ctx.svc.lineage(n, max_depth=1)
    assert {node.id for node in shallow} == {a.id, b.id}


async def _org_of(db: AsyncSession, ctx: Ctx):
    from app.models import Organization

    org = await db.get(Organization, ctx.project.organization_id)
    assert org is not None
    return org
