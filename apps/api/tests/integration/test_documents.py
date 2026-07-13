"""Document API integration tests (FR-4.5.*).

Drives the real FastAPI app against Postgres. Proves the route wiring, the
404-not-403 membership policy, the contributor/approver RBAC split, and the
optimistic-lock 409 surfacing.
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
    def __init__(self, admin: User, org_id: uuid.UUID, project_id: uuid.UUID) -> None:
        self.admin = admin
        self.org_id = org_id
        self.project_id = project_id


async def _seed(client: AsyncClient, db: AsyncSession, key: str = "DOC") -> Seed:
    org = await make_org(db)
    admin = await make_user(db, org, org_role=OrgRole.org_admin)
    await db.commit()
    proj = (
        await client.post(
            "/api/v1/projects",
            headers=_bearer(admin),
            json={"key": key, "name": key, "methodology": "agile"},
        )
    ).json()
    return Seed(admin, org.id, uuid.UUID(proj["id"]))


async def _add_member(
    db: AsyncSession, project_id: uuid.UUID, org_id: uuid.UUID, role: ProjectRole
) -> User:
    project = await db.get(Project, project_id)
    org_obj = await db.get(Organization, org_id)
    assert project is not None and org_obj is not None
    user = await make_user(db, org_obj)
    await make_member(db, project, user, role)
    await db.commit()
    return user


async def _create_doc(client: AsyncClient, seed: Seed, user: User) -> dict[str, object]:
    r = await client.post(
        f"/api/v1/projects/{seed.project_id}/documents",
        headers=_bearer(user),
        json={"doc_type": "srs", "title": "SRS"},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _create_version(
    client: AsyncClient, seed: Seed, user: User, doc_id: str, **body: object
) -> object:
    return await client.post(
        f"/api/v1/projects/{seed.project_id}/documents/{doc_id}/versions",
        headers=_bearer(user),
        json=body,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_create_document_and_first_version(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    seed = await _seed(client, db_session)
    doc = await _create_doc(client, seed, seed.admin)
    assert doc["current_version_id"] is None

    r = await _create_version(
        client, seed, seed.admin, doc["id"], content_md="# hello", base_version_id=None
    )
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["version_no"] == 1
    assert v["status"] == "draft"


async def test_approve_flow_sets_current_version(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    seed = await _seed(client, db_session)
    doc = await _create_doc(client, seed, seed.admin)
    v = (
        await _create_version(
            client, seed, seed.admin, doc["id"], content_md="body", base_version_id=None
        )
    ).json()
    r = await client.post(
        f"/api/v1/projects/{seed.project_id}/documents/{doc['id']}/versions/{v['id']}/approve",
        headers=_bearer(seed.admin),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"

    got = await client.get(
        f"/api/v1/projects/{seed.project_id}/documents/{doc['id']}", headers=_bearer(seed.admin)
    )
    assert got.json()["current_version_id"] == v["id"]


async def test_list_documents_and_versions(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    doc = await _create_doc(client, seed, seed.admin)
    await _create_version(
        client, seed, seed.admin, doc["id"], content_md="v1", base_version_id=None
    )
    docs = await client.get(
        f"/api/v1/projects/{seed.project_id}/documents", headers=_bearer(seed.admin)
    )
    assert len(docs.json()) == 1
    versions = await client.get(
        f"/api/v1/projects/{seed.project_id}/documents/{doc['id']}/versions",
        headers=_bearer(seed.admin),
    )
    assert [x["version_no"] for x in versions.json()] == [1]


# ---------------------------------------------------------------------------
# Optimistic lock surfacing
# ---------------------------------------------------------------------------


async def test_stale_base_returns_409(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    doc = await _create_doc(client, seed, seed.admin)
    await _create_version(
        client, seed, seed.admin, doc["id"], content_md="v1", base_version_id=None
    )
    r = await _create_version(
        client, seed, seed.admin, doc["id"], content_md="v2", base_version_id=None
    )
    assert r.status_code == 409
    assert r.json()["code"] == "version_conflict"


# ---------------------------------------------------------------------------
# RBAC + 404-not-403
# ---------------------------------------------------------------------------


async def test_non_member_gets_404(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    org = await db_session.get(Organization, seed.org_id)
    assert org is not None
    outsider = await make_user(db_session, org)  # not a project member
    await db_session.commit()
    r = await client.get(f"/api/v1/projects/{seed.project_id}/documents", headers=_bearer(outsider))
    assert r.status_code == 404


async def test_viewer_cannot_create_document(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    viewer = await _add_member(db_session, seed.project_id, seed.org_id, ProjectRole.viewer)
    r = await client.post(
        f"/api/v1/projects/{seed.project_id}/documents",
        headers=_bearer(viewer),
        json={"doc_type": "srs", "title": "nope"},
    )
    assert r.status_code == 403


async def test_developer_cannot_approve(client: AsyncClient, db_session: AsyncSession) -> None:
    seed = await _seed(client, db_session)
    dev = await _add_member(db_session, seed.project_id, seed.org_id, ProjectRole.developer)
    doc = await _create_doc(client, seed, seed.admin)
    v = (
        await _create_version(client, seed, dev, doc["id"], content_md="body", base_version_id=None)
    ).json()
    r = await client.post(
        f"/api/v1/projects/{seed.project_id}/documents/{doc['id']}/versions/{v['id']}/approve",
        headers=_bearer(dev),
    )
    assert r.status_code == 403
    assert r.json()["code"] == "insufficient_role"
