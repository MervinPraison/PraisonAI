"""
Integration tests for new gap API routes:
- Agent CRUD routes
- Label routes + issue linking
- Dependency routes
- Activity log routes
- Issue numbering in API
- Threaded comments in API
- Pagination query params
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
    await reset_engine()
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
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _auth(client) -> tuple:
    """Register and return (token, user_id, headers, workspace_id)."""
    resp = await client.post("/api/v1/auth/register", json={
        "email": "gap@test.com", "password": "testpass", "name": "GapUser",
    })
    data = resp.json()
    token = data["token"]
    user_id = data["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post("/api/v1/workspaces/", json={
        "name": "GapWS", "slug": "gapws",
    }, headers=headers)
    ws_id = resp.json()["id"]
    return token, user_id, headers, ws_id


class TestAgentRoutes:
    @pytest.mark.asyncio
    async def test_agent_crud(self, client):
        _, _, headers, ws_id = await _auth(client)

        # Create
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/agents/",
            json={"name": "TestBot", "instructions": "Help users"},
            headers=headers,
        )
        assert resp.status_code == 201
        agent = resp.json()
        agent_id = agent["id"]
        assert agent["name"] == "TestBot"
        assert agent["instructions"] == "Help users"
        assert agent["status"] == "offline"

        # List
        resp = await client.get(f"/api/v1/workspaces/{ws_id}/agents/", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        # Get
        resp = await client.get(f"/api/v1/workspaces/{ws_id}/agents/{agent_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "TestBot"

        # Update
        resp = await client.patch(
            f"/api/v1/workspaces/{ws_id}/agents/{agent_id}",
            json={"name": "UpdatedBot", "status": "idle"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "UpdatedBot"
        assert resp.json()["status"] == "idle"

        # Delete
        resp = await client.delete(
            f"/api/v1/workspaces/{ws_id}/agents/{agent_id}",
            headers=headers,
        )
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_agent_not_found(self, client):
        _, _, headers, ws_id = await _auth(client)
        resp = await client.get(
            f"/api/v1/workspaces/{ws_id}/agents/nonexistent",
            headers=headers,
        )
        assert resp.status_code == 404


class TestLabelRoutes:
    @pytest.mark.asyncio
    async def test_label_crud_and_linking(self, client):
        _, _, headers, ws_id = await _auth(client)

        # Create label
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/labels",
            json={"name": "bug", "color": "#FF0000"},
            headers=headers,
        )
        assert resp.status_code == 201
        label = resp.json()
        label_id = label["id"]
        assert label["name"] == "bug"

        # List labels
        resp = await client.get(f"/api/v1/workspaces/{ws_id}/labels", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        # Create issue
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/issues/",
            json={"title": "Labeled bug"},
            headers=headers,
        )
        issue_id = resp.json()["id"]

        # Add label to issue
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/issues/{issue_id}/labels/{label_id}",
            headers=headers,
        )
        assert resp.status_code == 204

        # List issue labels
        resp = await client.get(
            f"/api/v1/workspaces/{ws_id}/issues/{issue_id}/labels",
            headers=headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        # Remove label from issue
        resp = await client.delete(
            f"/api/v1/workspaces/{ws_id}/issues/{issue_id}/labels/{label_id}",
            headers=headers,
        )
        assert resp.status_code == 204

        # Delete label
        resp = await client.delete(
            f"/api/v1/workspaces/{ws_id}/labels/{label_id}",
            headers=headers,
        )
        assert resp.status_code == 204


class TestDependencyRoutes:
    @pytest.mark.asyncio
    async def test_dependency_crud(self, client):
        _, _, headers, ws_id = await _auth(client)

        # Create two issues
        resp1 = await client.post(f"/api/v1/workspaces/{ws_id}/issues/", json={"title": "Blocker"}, headers=headers)
        resp2 = await client.post(f"/api/v1/workspaces/{ws_id}/issues/", json={"title": "Blocked"}, headers=headers)
        i1_id = resp1.json()["id"]
        i2_id = resp2.json()["id"]

        # Create dependency
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/issues/{i1_id}/dependencies/",
            json={"depends_on_issue_id": i2_id, "type": "blocks"},
            headers=headers,
        )
        assert resp.status_code == 201
        dep = resp.json()
        dep_id = dep["id"]
        assert dep["type"] == "blocks"

        # List dependencies
        resp = await client.get(
            f"/api/v1/workspaces/{ws_id}/issues/{i1_id}/dependencies/",
            headers=headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        # Delete dependency
        resp = await client.delete(
            f"/api/v1/workspaces/{ws_id}/issues/{i1_id}/dependencies/{dep_id}",
            headers=headers,
        )
        assert resp.status_code == 204


class TestActivityRoutes:
    @pytest.mark.asyncio
    async def test_activity_routes(self, client):
        _, _, headers, ws_id = await _auth(client)

        # Create an issue (triggers activity logging)
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/issues/",
            json={"title": "Activity test"},
            headers=headers,
        )
        assert resp.status_code == 201
        issue_id = resp.json()["id"]

        # List workspace activity
        resp = await client.get(
            f"/api/v1/workspaces/{ws_id}/activity",
            headers=headers,
        )
        assert resp.status_code == 200
        activities = resp.json()
        assert len(activities) >= 1
        assert any(a["action"] == "issue.created" for a in activities)

        # List issue activity
        resp = await client.get(
            f"/api/v1/workspaces/{ws_id}/issues/{issue_id}/activity",
            headers=headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


class TestIssueNumberingAPI:
    @pytest.mark.asyncio
    async def test_issue_has_number_and_identifier(self, client):
        _, _, headers, ws_id = await _auth(client)

        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/issues/",
            json={"title": "Numbered Issue 1"},
            headers=headers,
        )
        assert resp.status_code == 201
        issue1 = resp.json()
        assert issue1["number"] == 1
        assert issue1["identifier"] == "ISS-1"

        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/issues/",
            json={"title": "Numbered Issue 2"},
            headers=headers,
        )
        issue2 = resp.json()
        assert issue2["number"] == 2
        assert issue2["identifier"] == "ISS-2"


class TestThreadedCommentsAPI:
    @pytest.mark.asyncio
    async def test_threaded_comment(self, client):
        _, _, headers, ws_id = await _auth(client)

        # Create issue
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/issues/",
            json={"title": "Thread test"},
            headers=headers,
        )
        issue_id = resp.json()["id"]

        # Top-level comment
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/issues/{issue_id}/comments",
            json={"content": "Parent comment"},
            headers=headers,
        )
        assert resp.status_code == 201
        parent = resp.json()
        assert parent["parent_id"] is None

        # Reply
        resp = await client.post(
            f"/api/v1/workspaces/{ws_id}/issues/{issue_id}/comments",
            json={"content": "Reply", "parent_id": parent["id"]},
            headers=headers,
        )
        assert resp.status_code == 201
        reply = resp.json()
        assert reply["parent_id"] == parent["id"]


class TestPaginationAPI:
    @pytest.mark.asyncio
    async def test_issue_list_pagination(self, client):
        _, _, headers, ws_id = await _auth(client)

        for i in range(5):
            await client.post(
                f"/api/v1/workspaces/{ws_id}/issues/",
                json={"title": f"Issue {i}"},
                headers=headers,
            )

        resp = await client.get(
            f"/api/v1/workspaces/{ws_id}/issues/?limit=2&offset=0",
            headers=headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

        resp = await client.get(
            f"/api/v1/workspaces/{ws_id}/issues/?limit=2&offset=2",
            headers=headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_agent_list_pagination(self, client):
        _, _, headers, ws_id = await _auth(client)

        for i in range(4):
            await client.post(
                f"/api/v1/workspaces/{ws_id}/agents/",
                json={"name": f"Agent {i}"},
                headers=headers,
            )

        resp = await client.get(
            f"/api/v1/workspaces/{ws_id}/agents/?limit=2&offset=0",
            headers=headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2
