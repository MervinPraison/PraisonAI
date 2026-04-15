"""
Integration tests: Full API flow via httpx.AsyncClient + TestClient.

Tests the complete flow: register → login → create workspace → add member →
create project → create issue → assign agent → comment.
"""

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ["PLATFORM_JWT_SECRET"] = "test-secret-for-testing-only"

from praisonai_platform.api.app import create_app
from praisonai_platform.db.base import Base, reset_engine

from sqlalchemy.ext.asyncio import create_async_engine


@pytest_asyncio.fixture
async def app():
    """Create a fresh app with in-memory DB for each test."""
    await reset_engine()
    # Patch the engine for testing
    from praisonai_platform.db import base as base_mod
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    base_mod._engine = eng
    base_mod._session_factory = None
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    application = create_app()
    yield application
    await eng.dispose()
    base_mod._engine = None
    base_mod._session_factory = None


@pytest_asyncio.fixture
async def client(app):
    """httpx async client for the app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestFullFlow:
    """End-to-end: register → workspace → project → issue → comment."""

    @pytest.mark.asyncio
    async def test_complete_flow(self, client):
        # 1. Register
        resp = await client.post("/api/v1/auth/register", json={
            "email": "flow@test.com",
            "password": "testpass",
            "name": "Flow User",
        })
        assert resp.status_code == 201
        data = resp.json()
        token = data["token"]
        user_id = data["user"]["id"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Login
        resp = await client.post("/api/v1/auth/login", json={
            "email": "flow@test.com",
            "password": "testpass",
        })
        assert resp.status_code == 200
        assert resp.json()["token"]

        # 3. Create workspace
        resp = await client.post("/api/v1/workspaces/", json={
            "name": "Acme Corp",
            "slug": "acme",
        }, headers=headers)
        assert resp.status_code == 201
        ws = resp.json()
        ws_id = ws["id"]
        assert ws["slug"] == "acme"

        # 4. List workspaces
        resp = await client.get("/api/v1/workspaces/", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

        # 5. Get workspace
        resp = await client.get(f"/api/v1/workspaces/{ws_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Acme Corp"

        # 6. List members (owner should be auto-added)
        resp = await client.get(f"/api/v1/workspaces/{ws_id}/members", headers=headers)
        assert resp.status_code == 200
        members = resp.json()
        assert len(members) >= 1
        assert any(m["role"] == "owner" for m in members)

        # 7. Create project
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/projects/",
            json={"title": "Platform MVP", "description": "Build the platform"},
            headers=headers,
        )
        assert resp.status_code == 201
        project = resp.json()
        project_id = project["id"]
        assert project["title"] == "Platform MVP"

        # 8. List projects
        resp = await client.get(f"/api/v1/workspaces/{ws_id}/projects/", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        # 9. Create issue
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/issues/",
            json={
                "title": "Implement auth",
                "description": "JWT + bcrypt",
                "project_id": project_id,
                "priority": "high",
            },
            headers=headers,
        )
        assert resp.status_code == 201
        issue = resp.json()
        issue_id = issue["id"]
        assert issue["priority"] == "high"
        assert issue["creator_id"] == user_id

        # 10. Update issue (assign to agent)
        resp = await client.patch(
            f"/api/v1/workspaces/{ws_id}/issues/{issue_id}",
            json={"assignee_type": "agent", "assignee_id": "agent-42", "status": "in_progress"},
            headers=headers,
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["assignee_type"] == "agent"
        assert updated["assignee_id"] == "agent-42"
        assert updated["status"] == "in_progress"

        # 11. Add comment
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/issues/{issue_id}/comments",
            json={"content": "Starting work on this now."},
            headers=headers,
        )
        assert resp.status_code == 201
        comment = resp.json()
        assert comment["content"] == "Starting work on this now."

        # 12. List comments
        resp = await client.get(
            f"/api/v1/workspaces/{ws_id}/issues/{issue_id}/comments",
            headers=headers,
        )
        assert resp.status_code == 200
        comments = resp.json()
        assert len(comments) == 1

        # 13. Project stats
        resp = await client.get(
            f"/api/v1/workspaces/{ws_id}/projects/{project_id}/stats",
            headers=headers,
        )
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["total"] == 1
        assert stats["by_status"]["in_progress"] == 1


class TestAuthErrors:
    @pytest.mark.asyncio
    async def test_missing_auth(self, client):
        resp = await client.get("/api/v1/workspaces/")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_bad_token(self, client):
        resp = await client.get(
            "/api/v1/workspaces/",
            headers={"Authorization": "Bearer bad-token"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_password(self, client):
        await client.post("/api/v1/auth/register", json={
            "email": "wrong@test.com",
            "password": "correct",
        })
        resp = await client.post("/api/v1/auth/login", json={
            "email": "wrong@test.com",
            "password": "incorrect",
        })
        assert resp.status_code == 401


class TestNotFound:
    @pytest.mark.asyncio
    async def test_workspace_not_found(self, client):
        # Register to get a token
        resp = await client.post("/api/v1/auth/register", json={
            "email": "notfound@test.com",
            "password": "pass",
        })
        token = resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/v1/workspaces/nonexistent", headers=headers)
        # With RBAC enforcement, non-members get 403 (no info leakage about existence)
        assert resp.status_code == 403
