"""Integration tests for health endpoints — Gate 0 requirement."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_ok(client: AsyncClient):
    response = await client.get("/health/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "inbox-chief-of-staff"


@pytest.mark.asyncio
async def test_health_ready_returns_checks(client: AsyncClient):
    response = await client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "checks" in data
    assert "db" in data["checks"]
