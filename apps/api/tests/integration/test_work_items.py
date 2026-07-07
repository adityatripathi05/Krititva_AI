"""Work Item Engine integration tests (FR-4.4.1-4.4.9).

Drives the real FastAPI app against Postgres. Covers hierarchy enforcement, the
full state-machine branch set (no edge / role required / role denied / role
allowed / owner override / hard gate), cycle-safe linking, lexorank rerank,
per-item bulk transition, and derived_from lineage.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Organization, OrgRole, Project, ProjectRole, User
from app.security.jwt import encode_access_token
from tests.integration._factories import make_member, make_org, make_user

pytestmark = pytest.mark.integration


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user.id)}"}


class Seed:
    def __init__(
        self,
        admin: User,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        project_key: str,
        states: dict[str, str],
    ) -> None:
        self.admin = admin
        self.org_id = org_id
        self.project_id = project_id
        self.project_key = project_key
        self.states = states


async def _seed(
    client: AsyncClient, db: AsyncSession, methodology: str = "agile", key: str = "WI"
) -> Seed:
    org = await make_org(db)
    admin = await make_user(db, org, org_role=OrgRole.org_admin)
    await db.commit()
    proj = (
        await client.post(
            "/api/v1/projects",
            headers=_bearer(admin),
            json={"key": key, "name": key, "methodology": methodology},
        )
    ).json()
    pid = proj["id"]
    states_resp = await client.get(
        f"/api/v1/projects/{pid}/workflow/states", headers=_bearer(admin)
    )
    states = {s["key"]: s["id"] for s in states_resp.json()}
    return Seed(admin, org.id, uuid.UUID(pid), proj["key"], states)


async def _create(client: AsyncClient, seed: Seed, user: User, **body: object) -> dict[str, object]:
    r = await client.post(
        f"/api/v1/projects/{seed.project_id}/work_items",
        headers=_bearer(user),
        json=body,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _add_member(
    db: AsyncSession, project_id: uuid.UUID, org_id: uuid.UUID, role: ProjectRole
) -> User:
    project = await db.get(Project, project_id)
    org_obj = await db.get(Organization, org_id)
    assert project is not None
    assert org_obj is not None
    user = await make_user(db, org_obj)
    await make_member(db, project, user, role)
    await db.commit()
    return user


async def _transition(
    client: AsyncClient, seed: Seed, user: User, item_id: str, to_state: str
) -> object:
    return await client.post(
        f"/api/v1/projects/{seed.project_id}/work_items/{item_id}/transitions",
        headers=_bearer(user),
        json={"to_state_id": seed.states[to_state]},
    )


# ---------------------------------------------------------------------------
# Create · seq · human key · hierarchy
# ---------------------------------------------------------------------------


async def test_create_sets_key_seq_state_rank(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    seed = await _seed(client, db_session, key="ACME")
    item = await _create(client, seed, seed.admin, kind="epic", title="Login epic")
    assert item["seq"] == 1
    assert item["key"] == "ACME-1"
    assert item["state_id"] == seed.states["backlog"]
    assert item["rank"] is not None
    assert item["ai_generated"] is False


async def test_seq_increments_per_project(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    a = await _create(client, seed, seed.admin, kind="epic", title="A")
    b = await _create(client, seed, seed.admin, kind="epic", title="B")
    assert (a["seq"], b["seq"]) == (1, 2)


async def test_hierarchy_allowed_pair(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    epic = await _create(client, seed, seed.admin, kind="epic", title="E")
    feature = await _create(
        client, seed, seed.admin, kind="feature", title="F", parent_id=epic["id"]
    )
    assert feature["parent_id"] == epic["id"]


async def test_hierarchy_violation_returns_pair(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    seed = await _seed(client, db_session)
    epic = await _create(client, seed, seed.admin, kind="epic", title="E")
    r = await client.post(
        f"/api/v1/projects/{seed.project_id}/work_items",
        headers=_bearer(seed.admin),
        json={"kind": "task", "title": "T", "parent_id": epic["id"]},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "hierarchy_violation"
    assert body["detail"] == {"parent_kind": "epic", "child_kind": "task"}


async def test_hierarchy_missing_parent_404(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    r = await client.post(
        f"/api/v1/projects/{seed.project_id}/work_items",
        headers=_bearer(seed.admin),
        json={"kind": "feature", "title": "F", "parent_id": str(uuid.uuid4())},
    )
    assert r.status_code == 404


async def test_viewer_cannot_create(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    viewer = await _add_member(db_session, seed.project_id, seed.org_id, ProjectRole.viewer)
    r = await client.post(
        f"/api/v1/projects/{seed.project_id}/work_items",
        headers=_bearer(viewer),
        json={"kind": "epic", "title": "nope"},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# State machine — every branch
# ---------------------------------------------------------------------------


async def test_transition_valid_edge(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    item = await _create(client, seed, seed.admin, kind="story", title="S")
    r = await _transition(client, seed, seed.admin, item["id"], "in_progress")
    assert r.status_code == 200
    assert r.json()["state_id"] == seed.states["in_progress"]


async def test_transition_no_edge_422(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    item = await _create(client, seed, seed.admin, kind="story", title="S")
    r = await _transition(client, seed, seed.admin, item["id"], "done")  # backlog->done: no edge
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_transition"


async def _drive_to_qa(client: AsyncClient, seed: Seed, user: User, item_id: str) -> None:
    for state in ("in_progress", "in_review", "qa"):
        r = await _transition(client, seed, user, item_id, state)
        assert r.status_code == 200, r.text


async def test_transition_owner_override_required_role(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """qa->done requires role 'qa'; the project_owner may still execute it."""
    seed = await _seed(client, db_session)
    item = await _create(client, seed, seed.admin, kind="story", title="S")
    await _drive_to_qa(client, seed, seed.admin, item["id"])
    r = await _transition(client, seed, seed.admin, item["id"], "done")
    assert r.status_code == 200
    assert r.json()["state_id"] == seed.states["done"]


async def test_transition_required_role_allowed_for_matching(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    seed = await _seed(client, db_session)
    qa_user = await _add_member(db_session, seed.project_id, seed.org_id, ProjectRole.qa)
    item = await _create(client, seed, seed.admin, kind="story", title="S")
    await _drive_to_qa(client, seed, seed.admin, item["id"])
    r = await _transition(client, seed, qa_user, item["id"], "done")
    assert r.status_code == 200


async def test_transition_required_role_denied(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    seed = await _seed(client, db_session)
    dev = await _add_member(db_session, seed.project_id, seed.org_id, ProjectRole.developer)
    item = await _create(client, seed, seed.admin, kind="story", title="S")
    await _drive_to_qa(client, seed, seed.admin, item["id"])
    r = await _transition(client, seed, dev, item["id"], "done")
    assert r.status_code == 403
    assert r.json()["code"] == "insufficient_role"


async def test_hard_gate_blocks_until_approval(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Waterfall gate_review->done is a hard gate — 409 until an approved milestone (M2)."""
    seed = await _seed(client, db_session, methodology="waterfall", key="WF")
    item = await _create(client, seed, seed.admin, kind="deliverable", title="D")
    for state in ("in_progress", "gate_review"):
        assert (await _transition(client, seed, seed.admin, item["id"], state)).status_code == 200
    r = await _transition(client, seed, seed.admin, item["id"], "done")
    assert r.status_code == 409
    assert r.json()["code"] == "gate_not_approved"


# ---------------------------------------------------------------------------
# Links + cycle detection + lineage
# ---------------------------------------------------------------------------


async def _link(
    client: AsyncClient, seed: Seed, user: User, from_id: str, to_id: str, link_type: str
) -> object:
    return await client.post(
        f"/api/v1/projects/{seed.project_id}/work_items/{from_id}/links",
        headers=_bearer(user),
        json={"to_item": to_id, "link_type": link_type},
    )


async def test_link_and_lineage(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    story = await _create(client, seed, seed.admin, kind="story", title="Story")
    task = await _create(client, seed, seed.admin, kind="task", title="Task")
    r = await _link(client, seed, seed.admin, task["id"], story["id"], "derived_from")
    assert r.status_code == 201

    lineage = await client.get(
        f"/api/v1/projects/{seed.project_id}/work_items/{task['id']}/lineage",
        headers=_bearer(seed.admin),
    )
    nodes = lineage.json()
    assert len(nodes) == 1
    assert nodes[0]["id"] == story["id"]
    assert nodes[0]["depth"] == 1


async def test_derived_from_cycle_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    a = await _create(client, seed, seed.admin, kind="story", title="A")
    b = await _create(client, seed, seed.admin, kind="story", title="B")
    assert (
        await _link(client, seed, seed.admin, a["id"], b["id"], "derived_from")
    ).status_code == 201
    r = await _link(client, seed, seed.admin, b["id"], a["id"], "derived_from")
    assert r.status_code == 422
    assert r.json()["code"] == "link_cycle_detected"


async def test_link_self_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    a = await _create(client, seed, seed.admin, kind="story", title="A")
    r = await _link(client, seed, seed.admin, a["id"], a["id"], "derived_from")
    assert r.status_code == 422


async def test_lineage_empty_for_leaf(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    a = await _create(client, seed, seed.admin, kind="story", title="A")
    r = await client.get(
        f"/api/v1/projects/{seed.project_id}/work_items/{a['id']}/lineage",
        headers=_bearer(seed.admin),
    )
    assert r.json() == []


# ---------------------------------------------------------------------------
# Rerank + bulk transition
# ---------------------------------------------------------------------------


async def test_rerank_between_neighbors(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    a = await _create(client, seed, seed.admin, kind="story", title="A")
    b = await _create(client, seed, seed.admin, kind="story", title="B")
    c = await _create(client, seed, seed.admin, kind="story", title="C")
    # created ranks are increasing a<b<c; move c between a and b.
    r = await client.post(
        f"/api/v1/projects/{seed.project_id}/work_items/{c['id']}/rerank",
        headers=_bearer(seed.admin),
        json={"before_id": a["id"], "after_id": b["id"]},
    )
    assert r.status_code == 200
    new_rank = r.json()["rank"]
    assert a["rank"] < new_rank < b["rank"]


async def test_bulk_transition_per_item_result(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    seed = await _seed(client, db_session)
    a = await _create(client, seed, seed.admin, kind="story", title="A")
    b = await _create(client, seed, seed.admin, kind="story", title="B")
    # Move `b` to in_progress first, so the bulk backlog->in_progress fails for it.
    assert (await _transition(client, seed, seed.admin, b["id"], "in_progress")).status_code == 200

    r = await client.post(
        f"/api/v1/projects/{seed.project_id}/work_items/bulk-transition",
        headers=_bearer(seed.admin),
        json={"item_ids": [a["id"], b["id"]], "to_state_id": seed.states["in_progress"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["succeeded"] == 1
    assert body["failed"] == 1
    by_id = {row["id"]: row for row in body["results"]}
    assert by_id[a["id"]]["ok"] is True
    assert by_id[b["id"]]["ok"] is False
    assert by_id[b["id"]]["error_code"] == "invalid_transition"

    # The successful item actually moved; failure did not roll it back.
    a_now = await client.get(
        f"/api/v1/projects/{seed.project_id}/work_items/{a['id']}", headers=_bearer(seed.admin)
    )
    assert a_now.json()["state_id"] == seed.states["in_progress"]


# ---------------------------------------------------------------------------
# In-use config safety (#3) + reference validation (#7) — review fixes
# ---------------------------------------------------------------------------


async def test_hierarchy_replace_rejects_in_use_pair(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    seed = await _seed(client, db_session)
    epic = await _create(client, seed, seed.admin, kind="epic", title="E")
    await _create(client, seed, seed.admin, kind="feature", title="F", parent_id=epic["id"])
    # epic->feature is now realized by live items; removing it must be refused.
    r = await client.patch(
        f"/api/v1/projects/{seed.project_id}/hierarchy-rules",
        headers=_bearer(seed.admin),
        json={"rules": [{"parent_kind": "story", "child_kind": "task"}]},
    )
    assert r.status_code == 409
    assert r.json()["code"] == "config_in_use"


async def test_reseed_blocked_when_items_exist(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    seed = await _seed(client, db_session)
    await _create(client, seed, seed.admin, kind="epic", title="E")
    r = await client.patch(
        f"/api/v1/projects/{seed.project_id}/methodology",
        headers=_bearer(seed.admin),
        json={"methodology": "waterfall", "reseed_workflow": True},
    )
    assert r.status_code == 409
    assert r.json()["code"] == "config_in_use"


async def test_create_rejects_non_member_assignee(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    seed = await _seed(client, db_session)
    org = await db_session.get(Organization, seed.org_id)
    assert org is not None
    outsider = await make_user(db_session, org)  # exists, but not a project member
    await db_session.commit()
    r = await client.post(
        f"/api/v1/projects/{seed.project_id}/work_items",
        headers=_bearer(seed.admin),
        json={"kind": "story", "title": "S", "assignee_id": str(outsider.id)},
    )
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_reference"


async def test_create_accepts_member_assignee(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    seed = await _seed(client, db_session)
    dev = await _add_member(db_session, seed.project_id, seed.org_id, ProjectRole.developer)
    r = await client.post(
        f"/api/v1/projects/{seed.project_id}/work_items",
        headers=_bearer(seed.admin),
        json={"kind": "story", "title": "S", "assignee_id": str(dev.id)},
    )
    assert r.status_code == 201
    assert r.json()["assignee_id"] == str(dev.id)
