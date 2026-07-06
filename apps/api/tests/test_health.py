"""Health probes (FR-4.12, NFR-5.3.1)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_livez(client: AsyncClient) -> None:
    resp = await client.get("/livez")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body
