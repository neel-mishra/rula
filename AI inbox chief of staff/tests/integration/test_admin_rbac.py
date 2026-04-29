"""Integration tests for admin RBAC endpoints."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.main import app
from core.db import get_db
from core.models.user import User, UserRole
from core.security.auth import create_session_token


async def _make_user(db, *, email: str, role: UserRole) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        display_name=email.split("@")[0],
        is_active=True,
        role=role,
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def rbac_clients(db_session):
    async def override_get_db():
        yield db_session

    admin_user = await _make_user(db_session, email="admin@test", role=UserRole.ADMIN)
    normal_user = await _make_user(db_session, email="user@test", role=UserRole.USER)

    admin_token = create_session_token(admin_user.id, admin_user.email)
    user_token = create_session_token(normal_user.id, normal_user.email)

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as admin_client:
        admin_client.headers["Authorization"] = f"Bearer {admin_token}"
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as user_client:
            user_client.headers["Authorization"] = f"Bearer {user_token}"
            yield admin_client, user_client, admin_user, normal_user
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_non_admin_forbidden_on_users(rbac_clients):
    _admin, user_client, _a, _u = rbac_clients
    resp = await user_client.get("/admin/users")
    assert resp.status_code == 403
    assert "Admin role required" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_non_admin_forbidden_on_activity_stats(rbac_clients):
    _admin, user_client, _a, _u = rbac_clients
    resp = await user_client.get("/admin/activity-stats")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_list_users(rbac_clients):
    admin_client, _u, admin_user, normal_user = rbac_clients
    resp = await admin_client.get("/admin/users")
    assert resp.status_code == 200
    data = resp.json()
    ids = {u["id"] for u in data["users"]}
    assert str(admin_user.id) in ids
    assert str(normal_user.id) in ids
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_admin_activity_stats_shape(rbac_clients):
    admin_client, *_ = rbac_clients
    resp = await admin_client.get("/admin/activity-stats?window_days=14")
    assert resp.status_code == 200
    data = resp.json()
    assert data["window_days"] == 14
    assert "total_users" in data
    assert "active_users_in_window" in data
    assert "triage_decisions" in data
    assert "drafts_generated" in data
    assert "mutations_applied" in data
    assert "undos_performed" in data
    assert "critical_audit_events" in data


@pytest.mark.asyncio
async def test_admin_can_promote_user(rbac_clients, db_session):
    admin_client, _u, _a, normal_user = rbac_clients
    resp = await admin_client.patch(
        f"/admin/users/{normal_user.id}/role",
        json={"role": "admin"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"

    await db_session.refresh(normal_user)
    assert normal_user.role is UserRole.ADMIN


@pytest.mark.asyncio
async def test_admin_cannot_self_demote(rbac_clients):
    admin_client, _u, admin_user, _n = rbac_clients
    resp = await admin_client.patch(
        f"/admin/users/{admin_user.id}/role",
        json={"role": "user"},
    )
    assert resp.status_code == 400
    assert "cannot demote themselves" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_admin_invalid_role_400(rbac_clients):
    admin_client, _u, _a, normal_user = rbac_clients
    resp = await admin_client.patch(
        f"/admin/users/{normal_user.id}/role",
        json={"role": "superuser"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_admin_missing_user_404(rbac_clients):
    admin_client, *_ = rbac_clients
    resp = await admin_client.patch(
        f"/admin/users/{uuid.uuid4()}/role",
        json={"role": "admin"},
    )
    assert resp.status_code == 404
