"""RBAC dependency factories + 404-not-403 policy (§FR-4.1.4, §NFR-5.2.8).

Exercises ``require_project_membership`` and ``require_agent_permission`` via
a throwaway route mounted only in this test module (avoids waiting for
M0.T5 before we can prove the deps work).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_db,
    require_agent_permission,
    require_org_role,
    require_project_membership,
)
from app.api.errors import register_exception_handlers
from app.models import OrgRole, ProjectMember, ProjectRole, User
from app.security.jwt import encode_access_token
from tests.integration._factories import (
    make_member,
    make_org,
    make_project,
    make_user,
)

pytestmark = pytest.mark.integration


def _build_test_app(session: AsyncSession) -> FastAPI:
    """Fresh app with throwaway routes exercising the RBAC deps."""

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield session

    app = FastAPI()
    register_exception_handlers(app)
    app.dependency_overrides[get_db] = _override_get_db

    @app.get("/only-org-admin")
    async def only_org_admin(
        _: User = Depends(require_org_role(OrgRole.org_admin)),
    ) -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/projects/{project_id}/only-members")
    async def only_members(
        result: tuple[User, ProjectMember] = Depends(require_project_membership()),
    ) -> dict[str, str]:
        return {"role": result[1].role.value}

    @app.get("/projects/{project_id}/only-devs")
    async def only_devs(
        result: tuple[User, ProjectMember] = Depends(
            require_project_membership(ProjectRole.developer)
        ),
    ) -> dict[str, str]:
        return {"role": result[1].role.value}

    @app.get("/projects/{project_id}/agent-qa")
    async def agent_qa(
        result: tuple[User, ProjectMember] = Depends(require_agent_permission("qa")),
    ) -> dict[str, str]:
        return {"role": result[1].role.value}

    @app.get("/projects/{project_id}/agent-architect")
    async def agent_architect(
        result: tuple[User, ProjectMember] = Depends(require_agent_permission("architect")),
    ) -> dict[str, str]:
        return {"role": result[1].role.value}

    return app


@pytest_asyncio.fixture
async def rbac_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app = _build_test_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        yield ac


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {encode_access_token(user.id)}"}


# ---------------------------------------------------------------------------


async def test_require_org_role_allows_matching(
    rbac_client: AsyncClient, db_session: AsyncSession
) -> None:
    org = await make_org(db_session)
    admin = await make_user(db_session, org, org_role=OrgRole.org_admin)
    await db_session.commit()
    r = await rbac_client.get("/only-org-admin", headers=_bearer(admin))
    assert r.status_code == 200


async def test_require_org_role_denies_member(
    rbac_client: AsyncClient, db_session: AsyncSession
) -> None:
    org = await make_org(db_session)
    member = await make_user(db_session, org, org_role=OrgRole.member)
    await db_session.commit()
    r = await rbac_client.get("/only-org-admin", headers=_bearer(member))
    assert r.status_code == 403
    assert r.json()["code"] == "insufficient_role"


async def test_project_non_member_gets_404_not_403(
    rbac_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Cross-project reads must not leak project existence (§NFR-5.2.8)."""
    org = await make_org(db_session)
    project = await make_project(db_session, org)
    outsider = await make_user(db_session, org)
    await db_session.commit()

    r = await rbac_client.get(f"/projects/{project.id}/only-members", headers=_bearer(outsider))
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"


async def test_project_member_can_access(
    rbac_client: AsyncClient, db_session: AsyncSession
) -> None:
    org = await make_org(db_session)
    project = await make_project(db_session, org)
    user = await make_user(db_session, org)
    await make_member(db_session, project, user, ProjectRole.developer)
    await db_session.commit()

    r = await rbac_client.get(f"/projects/{project.id}/only-members", headers=_bearer(user))
    assert r.status_code == 200
    assert r.json()["role"] == "developer"


async def test_project_member_wrong_role_gets_403(
    rbac_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Right project, wrong project role → 403 (not 404) — caller can see it."""
    org = await make_org(db_session)
    project = await make_project(db_session, org)
    viewer = await make_user(db_session, org)
    await make_member(db_session, project, viewer, ProjectRole.viewer)
    await db_session.commit()

    r = await rbac_client.get(f"/projects/{project.id}/only-devs", headers=_bearer(viewer))
    assert r.status_code == 403


async def test_random_project_uuid_still_404(
    rbac_client: AsyncClient, db_session: AsyncSession
) -> None:
    """A well-formed but non-existent project id also returns 404 (no leak)."""
    org = await make_org(db_session)
    user = await make_user(db_session, org)
    await db_session.commit()
    r = await rbac_client.get(f"/projects/{uuid.uuid4()}/only-members", headers=_bearer(user))
    assert r.status_code == 404


async def test_agent_permission_matrix(rbac_client: AsyncClient, db_session: AsyncSession) -> None:
    """QA agent invocable by qa/developer/scrum_master/project_owner; not viewer."""
    org = await make_org(db_session)
    project = await make_project(db_session, org)
    qa_user = await make_user(db_session, org)
    viewer_user = await make_user(db_session, org)
    await make_member(db_session, project, qa_user, ProjectRole.qa)
    await make_member(db_session, project, viewer_user, ProjectRole.viewer)
    await db_session.commit()

    r_qa = await rbac_client.get(f"/projects/{project.id}/agent-qa", headers=_bearer(qa_user))
    assert r_qa.status_code == 200
    r_viewer = await rbac_client.get(
        f"/projects/{project.id}/agent-qa", headers=_bearer(viewer_user)
    )
    assert r_viewer.status_code == 403

    # QA role cannot invoke the Architect agent.
    r_qa_arch = await rbac_client.get(
        f"/projects/{project.id}/agent-architect", headers=_bearer(qa_user)
    )
    assert r_qa_arch.status_code == 403
