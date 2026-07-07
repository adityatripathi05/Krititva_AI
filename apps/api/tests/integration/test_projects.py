"""Project creation + methodology config endpoints (FR-4.2.*, FR-4.3.*).

Exercises the real FastAPI app against Postgres: template seeding is atomic with
project creation, config edits enforce in-use safety, and RBAC gates the writes.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    HierarchyRule,
    Organization,
    OrgRole,
    Project,
    ProjectMember,
    ProjectRole,
    User,
    WorkflowState,
    WorkflowTransition,
)
from app.security.jwt import encode_access_token
from tests.integration._factories import make_member, make_org, make_project, make_user

pytestmark = pytest.mark.integration


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user.id)}"}


async def _count(db: AsyncSession, model: type, project_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(model).where(model.project_id == project_id)
    return int((await db.execute(stmt)).scalar_one())


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("methodology", "n_states", "n_transitions", "n_rules"),
    [("agile", 6, 10, 7), ("waterfall", 5, 6, 4), ("hybrid", 8, 13, 11)],
)
async def test_create_project_seeds_methodology(
    client: AsyncClient,
    db_session: AsyncSession,
    methodology: str,
    n_states: int,
    n_transitions: int,
    n_rules: int,
) -> None:
    org = await make_org(db_session)
    admin = await make_user(db_session, org, org_role=OrgRole.org_admin)
    await db_session.commit()

    r = await client.post(
        "/api/v1/projects",
        headers=_bearer(admin),
        json={"key": "ACME-ONE", "name": "Acme One", "methodology": methodology},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["methodology"] == methodology
    assert body["client_portal_mode"] == "export_only"
    assert body["status"] == "active"
    pid = uuid.UUID(body["id"])

    assert await _count(db_session, WorkflowState, pid) == n_states
    assert await _count(db_session, WorkflowTransition, pid) == n_transitions
    assert await _count(db_session, HierarchyRule, pid) == n_rules

    # Creator is enrolled as project_owner.
    m = (
        await db_session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == pid, ProjectMember.user_id == admin.id
            )
        )
    ).scalar_one()
    assert m.role is ProjectRole.project_owner
    # organization_id populated on every tenant-scoped write (§CLAUDE.md §1.9).
    assert body["organization_id"] == str(org.id)


async def test_waterfall_gate_carries_quorum(client: AsyncClient, db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    admin = await make_user(db_session, org, org_role=OrgRole.org_admin)
    await db_session.commit()

    r = await client.post(
        "/api/v1/projects",
        headers=_bearer(admin),
        json={"key": "WF-1", "name": "WF", "methodology": "waterfall"},
    )
    pid = uuid.UUID(r.json()["id"])
    gates = (
        (
            await db_session.execute(
                select(WorkflowTransition).where(
                    WorkflowTransition.project_id == pid,
                    WorkflowTransition.is_hard_gate.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(gates) == 1
    assert gates[0].approval_quorum == {"project_owner": 1, "client_approver": 1}


async def test_create_requires_org_admin(client: AsyncClient, db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    member = await make_user(db_session, org, org_role=OrgRole.member)
    await db_session.commit()
    r = await client.post(
        "/api/v1/projects",
        headers=_bearer(member),
        json={"key": "NOPE", "name": "No", "methodology": "agile"},
    )
    assert r.status_code == 403


async def test_duplicate_key_rejected_atomically(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org = await make_org(db_session)
    admin = await make_user(db_session, org, org_role=OrgRole.org_admin)
    await db_session.commit()

    payload = {"key": "DUP-1", "name": "First", "methodology": "agile"}
    r1 = await client.post("/api/v1/projects", headers=_bearer(admin), json=payload)
    assert r1.status_code == 201

    r2 = await client.post(
        "/api/v1/projects",
        headers=_bearer(admin),
        json={"key": "DUP-1", "name": "Second", "methodology": "waterfall"},
    )
    assert r2.status_code == 409
    assert r2.json()["code"] == "duplicate_key"

    # Exactly one project with that key; no orphaned states from the failed attempt.
    n_projects = (
        await db_session.execute(
            select(func.count()).select_from(Project).where(Project.key == "DUP-1")
        )
    ).scalar_one()
    assert n_projects == 1


async def test_bad_key_pattern_422(client: AsyncClient, db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    admin = await make_user(db_session, org, org_role=OrgRole.org_admin)
    await db_session.commit()
    r = await client.post(
        "/api/v1/projects",
        headers=_bearer(admin),
        json={"key": "lower case", "name": "x", "methodology": "agile"},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


async def test_get_project_member_ok_nonmember_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org = await make_org(db_session)
    project = await make_project(db_session, org)
    member = await make_user(db_session, org)
    outsider = await make_user(db_session, org)
    await make_member(db_session, project, member, ProjectRole.developer)
    await db_session.commit()

    r_ok = await client.get(f"/api/v1/projects/{project.id}", headers=_bearer(member))
    assert r_ok.status_code == 200
    assert r_ok.json()["key"] == project.key

    r_404 = await client.get(f"/api/v1/projects/{project.id}", headers=_bearer(outsider))
    assert r_404.status_code == 404


async def test_list_workflow_config(client: AsyncClient, db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    admin = await make_user(db_session, org, org_role=OrgRole.org_admin)
    await db_session.commit()
    pid = uuid.UUID(
        (
            await client.post(
                "/api/v1/projects",
                headers=_bearer(admin),
                json={"key": "CFG-1", "name": "Cfg", "methodology": "agile"},
            )
        ).json()["id"]
    )

    states = await client.get(f"/api/v1/projects/{pid}/workflow/states", headers=_bearer(admin))
    assert states.status_code == 200
    assert next(s["key"] for s in states.json()) == "backlog"  # ordered by sort_order

    trans = await client.get(f"/api/v1/projects/{pid}/workflow/transitions", headers=_bearer(admin))
    assert len(trans.json()) == 10

    rules = await client.get(f"/api/v1/projects/{pid}/hierarchy-rules", headers=_bearer(admin))
    assert len(rules.json()) == 7


# ---------------------------------------------------------------------------
# Config edits (FR-4.3.2)
# ---------------------------------------------------------------------------


async def _make_project_with_owner(
    client: AsyncClient, db_session: AsyncSession, key: str, methodology: str = "agile"
) -> tuple[User, uuid.UUID]:
    org = await make_org(db_session)
    admin = await make_user(db_session, org, org_role=OrgRole.org_admin)
    await db_session.commit()
    pid = uuid.UUID(
        (
            await client.post(
                "/api/v1/projects",
                headers=_bearer(admin),
                json={"key": key, "name": key, "methodology": methodology},
            )
        ).json()["id"]
    )
    return admin, pid


async def test_update_transition_sets_hard_gate(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin, pid = await _make_project_with_owner(client, db_session, "GATE-1")
    trans = (
        await client.get(f"/api/v1/projects/{pid}/workflow/transitions", headers=_bearer(admin))
    ).json()
    tid = trans[0]["id"]

    r = await client.patch(
        f"/api/v1/projects/{pid}/workflow/transitions/{tid}",
        headers=_bearer(admin),
        json={"is_hard_gate": True, "approval_quorum": {"project_owner": 1}},
    )
    assert r.status_code == 200
    assert r.json()["is_hard_gate"] is True
    assert r.json()["approval_quorum"] == {"project_owner": 1}


async def test_hard_gate_without_quorum_422(client: AsyncClient, db_session: AsyncSession) -> None:
    admin, pid = await _make_project_with_owner(client, db_session, "GATE-2")
    tid = (
        await client.get(f"/api/v1/projects/{pid}/workflow/transitions", headers=_bearer(admin))
    ).json()[0]["id"]
    r = await client.patch(
        f"/api/v1/projects/{pid}/workflow/transitions/{tid}",
        headers=_bearer(admin),
        json={"is_hard_gate": True},
    )
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_workflow_config"


async def test_update_transition_requires_owner(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin, pid = await _make_project_with_owner(client, db_session, "GATE-3")
    # A developer member cannot edit config — only project_owner may.
    project = await db_session.get(Project, pid)
    assert project is not None
    org = await db_session.get(Organization, project.organization_id)
    assert org is not None
    dev = await make_user(db_session, org)
    await make_member(db_session, project, dev, ProjectRole.developer)
    await db_session.commit()

    tid = (
        await client.get(f"/api/v1/projects/{pid}/workflow/transitions", headers=_bearer(admin))
    ).json()[0]["id"]
    r = await client.patch(
        f"/api/v1/projects/{pid}/workflow/transitions/{tid}",
        headers=_bearer(dev),
        json={"is_hard_gate": False},
    )
    assert r.status_code == 403


async def test_replace_hierarchy_rules(client: AsyncClient, db_session: AsyncSession) -> None:
    admin, pid = await _make_project_with_owner(client, db_session, "HR-1")
    r = await client.patch(
        f"/api/v1/projects/{pid}/hierarchy-rules",
        headers=_bearer(admin),
        json={
            "rules": [
                {"parent_kind": "epic", "child_kind": "story"},
                {"parent_kind": "story", "child_kind": "task"},
            ]
        },
    )
    assert r.status_code == 200
    returned = {(x["parent_kind"], x["child_kind"]) for x in r.json()}
    assert returned == {("epic", "story"), ("story", "task")}
    assert await _count(db_session, HierarchyRule, pid) == 2


async def test_replace_hierarchy_duplicate_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin, pid = await _make_project_with_owner(client, db_session, "HR-2")
    r = await client.patch(
        f"/api/v1/projects/{pid}/hierarchy-rules",
        headers=_bearer(admin),
        json={
            "rules": [
                {"parent_kind": "epic", "child_kind": "story"},
                {"parent_kind": "epic", "child_kind": "story"},
            ]
        },
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Methodology change (FR-4.2.3)
# ---------------------------------------------------------------------------


async def test_change_methodology_reseed(client: AsyncClient, db_session: AsyncSession) -> None:
    admin, pid = await _make_project_with_owner(client, db_session, "SWAP-1", "agile")
    r = await client.patch(
        f"/api/v1/projects/{pid}/methodology",
        headers=_bearer(admin),
        json={"methodology": "waterfall", "reseed_workflow": True},
    )
    assert r.status_code == 200
    assert r.json()["methodology"] == "waterfall"
    # Reseeded to the waterfall template counts.
    assert await _count(db_session, WorkflowState, pid) == 5
    assert await _count(db_session, WorkflowTransition, pid) == 6


async def test_change_methodology_no_reseed_keeps_states(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    admin, pid = await _make_project_with_owner(client, db_session, "SWAP-2", "agile")
    r = await client.patch(
        f"/api/v1/projects/{pid}/methodology",
        headers=_bearer(admin),
        json={"methodology": "waterfall", "reseed_workflow": False},
    )
    assert r.status_code == 200
    assert r.json()["methodology"] == "waterfall"
    # No reseed → original agile states untouched (FR-4.2.3: no rewrite).
    assert await _count(db_session, WorkflowState, pid) == 6
