"""Integration tests for PlatformClient against the live API.

Tests every PlatformClient method through the full HTTP stack.
"""

from __future__ import annotations

import os
import pytest
import httpx
from httpx import ASGITransport

from praisonai_platform.api.app import create_app
from praisonai_platform.client.platform_client import PlatformClient
from praisonai_platform.db.base import Base, get_engine, reset_engine

os.environ.setdefault("PLATFORM_JWT_SECRET", "test-client-secret")


@pytest.fixture()
async def app():
    await reset_engine()
    _app = create_app()
    engine = get_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield _app
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    await reset_engine()


@pytest.fixture()
async def client(app):
    """PlatformClient wired to the ASGI app via httpx transport."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        pc = PlatformClient(base_url="http://test")
        pc._client = http
        pc._owned_client = True
        yield pc


# ── Auth ──────────────────────────────────────────────────────────────────

class TestClientAuth:
    @pytest.mark.asyncio
    async def test_register_and_login(self, client: PlatformClient):
        reg = await client.register("alice@test.com", "pass123", "Alice")
        assert "token" in reg
        assert reg["user"]["email"] == "alice@test.com"

        # Login with same creds
        login = await client.login("alice@test.com", "pass123")
        assert "token" in login

    @pytest.mark.asyncio
    async def test_get_me(self, client: PlatformClient):
        await client.register("me@test.com", "pass123", "Me")
        me = await client.get_me()
        assert me["email"] == "me@test.com"
        assert me["name"] == "Me"


# ── Workspaces ────────────────────────────────────────────────────────────

class TestClientWorkspaces:
    @pytest.mark.asyncio
    async def test_workspace_crud(self, client: PlatformClient):
        await client.register("ws@test.com", "pass123")

        # Create
        ws = await client.create_workspace("My Workspace", description="desc")
        ws_id = ws["id"]
        assert ws["name"] == "My Workspace"

        # List
        wss = await client.list_workspaces()
        assert len(wss) >= 1

        # Get
        got = await client.get_workspace(ws_id)
        assert got["id"] == ws_id

        # Update
        updated = await client.update_workspace(ws_id, name="Updated WS")
        assert updated["name"] == "Updated WS"

        # Delete
        await client.delete_workspace(ws_id)


# ── Members ───────────────────────────────────────────────────────────────

class TestClientMembers:
    @pytest.mark.asyncio
    async def test_member_operations(self, client: PlatformClient):
        await client.register("owner@test.com", "pass123")
        ws = await client.create_workspace("MemberWS")
        ws_id = ws["id"]

        # Register another user
        reg2 = await client.register("member@test.com", "pass123")
        user2_id = reg2["user"]["id"]

        # Re-login as owner
        await client.login("owner@test.com", "pass123")

        # Add member
        m = await client.add_member(ws_id, user2_id, "member")
        assert m["role"] == "member"

        # List
        members = await client.list_members(ws_id)
        assert len(members) >= 2

        # Update role
        updated = await client.update_member_role(ws_id, user2_id, "admin")
        assert updated["role"] == "admin"

        # Remove
        await client.remove_member(ws_id, user2_id)
        members2 = await client.list_members(ws_id)
        assert len(members2) == len(members) - 1


# ── Projects ──────────────────────────────────────────────────────────────

class TestClientProjects:
    @pytest.mark.asyncio
    async def test_project_crud(self, client: PlatformClient):
        await client.register("proj@test.com", "pass123")
        ws = await client.create_workspace("ProjWS")
        ws_id = ws["id"]

        # Create
        proj = await client.create_project(ws_id, "My Project", "desc")
        proj_id = proj["id"]
        assert proj["title"] == "My Project"

        # List
        projs = await client.list_projects(ws_id)
        assert len(projs) == 1

        # Get
        got = await client.get_project(ws_id, proj_id)
        assert got["id"] == proj_id

        # Update
        updated = await client.update_project(ws_id, proj_id, title="Updated")
        assert updated["title"] == "Updated"

        # Stats
        stats = await client.get_project_stats(ws_id, proj_id)
        assert isinstance(stats, dict)

        # Delete
        await client.delete_project(ws_id, proj_id)
        projs2 = await client.list_projects(ws_id)
        assert len(projs2) == 0


# ── Issues ────────────────────────────────────────────────────────────────

class TestClientIssues:
    @pytest.mark.asyncio
    async def test_issue_crud(self, client: PlatformClient):
        await client.register("issue@test.com", "pass123")
        ws = await client.create_workspace("IssueWS")
        ws_id = ws["id"]

        # Create
        issue = await client.create_issue(ws_id, "Bug 1", description="broken")
        issue_id = issue["id"]
        assert issue["title"] == "Bug 1"

        # List
        issues = await client.list_issues(ws_id)
        assert len(issues) == 1

        # Get
        got = await client.get_issue(ws_id, issue_id)
        assert got["id"] == issue_id

        # Update
        updated = await client.update_issue(ws_id, issue_id, status="in_progress")
        assert updated["status"] == "in_progress"

        # Delete
        await client.delete_issue(ws_id, issue_id)
        issues2 = await client.list_issues(ws_id)
        assert len(issues2) == 0

    @pytest.mark.asyncio
    async def test_issue_pagination(self, client: PlatformClient):
        await client.register("page@test.com", "pass123")
        ws = await client.create_workspace("PageWS")
        ws_id = ws["id"]

        for i in range(5):
            await client.create_issue(ws_id, f"Issue {i}")

        page1 = await client.list_issues(ws_id, limit=2, offset=0)
        assert len(page1) == 2

        page2 = await client.list_issues(ws_id, limit=2, offset=2)
        assert len(page2) == 2

    @pytest.mark.asyncio
    async def test_sub_issue(self, client: PlatformClient):
        await client.register("sub@test.com", "pass123")
        ws = await client.create_workspace("SubWS")
        ws_id = ws["id"]

        parent = await client.create_issue(ws_id, "Parent")
        child = await client.create_issue(ws_id, "Child", parent_issue_id=parent["id"])
        assert child["parent_issue_id"] == parent["id"]


# ── Comments ──────────────────────────────────────────────────────────────

class TestClientComments:
    @pytest.mark.asyncio
    async def test_comment_operations(self, client: PlatformClient):
        await client.register("comment@test.com", "pass123")
        ws = await client.create_workspace("CommentWS")
        ws_id = ws["id"]
        issue = await client.create_issue(ws_id, "Commentable")
        issue_id = issue["id"]

        # Add comment
        c = await client.add_comment(ws_id, issue_id, "Hello")
        assert c["content"] == "Hello"

        # Add reply
        reply = await client.add_comment(ws_id, issue_id, "Reply", parent_id=c["id"])
        assert reply["parent_id"] == c["id"]

        # List
        comments = await client.list_comments(ws_id, issue_id)
        assert len(comments) == 2


# ── Agents ────────────────────────────────────────────────────────────────

class TestClientAgents:
    @pytest.mark.asyncio
    async def test_agent_crud(self, client: PlatformClient):
        await client.register("agent@test.com", "pass123")
        ws = await client.create_workspace("AgentWS")
        ws_id = ws["id"]

        # Create
        agent = await client.create_agent(ws_id, "Bot-1", instructions="Do stuff")
        agent_id = agent["id"]
        assert agent["name"] == "Bot-1"
        assert agent["instructions"] == "Do stuff"

        # List
        agents = await client.list_agents(ws_id)
        assert len(agents) == 1

        # Get
        got = await client.get_agent(ws_id, agent_id)
        assert got["id"] == agent_id

        # Update
        updated = await client.update_agent(ws_id, agent_id, name="Bot-2")
        assert updated["name"] == "Bot-2"

        # Delete
        await client.delete_agent(ws_id, agent_id)
        agents2 = await client.list_agents(ws_id)
        assert len(agents2) == 0


# ── Labels ────────────────────────────────────────────────────────────────

class TestClientLabels:
    @pytest.mark.asyncio
    async def test_label_crud_and_linking(self, client: PlatformClient):
        await client.register("label@test.com", "pass123")
        ws = await client.create_workspace("LabelWS")
        ws_id = ws["id"]

        # Create label
        label = await client.create_label(ws_id, "bug", "#FF0000")
        label_id = label["id"]
        assert label["name"] == "bug"

        # List
        labels = await client.list_labels(ws_id)
        assert len(labels) == 1

        # Update
        updated = await client.update_label(ws_id, label_id, color="#00FF00")
        assert updated["color"] == "#00FF00"

        # Link to issue
        issue = await client.create_issue(ws_id, "Labeled")
        issue_id = issue["id"]

        await client.add_label_to_issue(ws_id, issue_id, label_id)

        # List issue labels
        issue_labels = await client.list_issue_labels(ws_id, issue_id)
        assert len(issue_labels) == 1
        assert issue_labels[0]["id"] == label_id

        # Remove from issue
        await client.remove_label_from_issue(ws_id, issue_id, label_id)
        issue_labels2 = await client.list_issue_labels(ws_id, issue_id)
        assert len(issue_labels2) == 0

        # Delete label
        await client.delete_label(ws_id, label_id)
        labels2 = await client.list_labels(ws_id)
        assert len(labels2) == 0


# ── Dependencies ──────────────────────────────────────────────────────────

class TestClientDependencies:
    @pytest.mark.asyncio
    async def test_dependency_operations(self, client: PlatformClient):
        await client.register("dep@test.com", "pass123")
        ws = await client.create_workspace("DepWS")
        ws_id = ws["id"]

        issue1 = await client.create_issue(ws_id, "Issue A")
        issue2 = await client.create_issue(ws_id, "Issue B")

        # Create dependency
        dep = await client.create_dependency(ws_id, issue1["id"], issue2["id"], "blocks")
        dep_id = dep["id"]
        assert dep["type"] == "blocks"

        # List
        deps = await client.list_dependencies(ws_id, issue1["id"])
        assert len(deps) == 1

        # Delete
        await client.delete_dependency(ws_id, issue1["id"], dep_id)
        deps2 = await client.list_dependencies(ws_id, issue1["id"])
        assert len(deps2) == 0


# ── Activity ──────────────────────────────────────────────────────────────

class TestClientActivity:
    @pytest.mark.asyncio
    async def test_activity_logs(self, client: PlatformClient):
        await client.register("act@test.com", "pass123")
        ws = await client.create_workspace("ActivityWS")
        ws_id = ws["id"]

        # Creating an issue should log activity
        issue = await client.create_issue(ws_id, "Track Me")
        issue_id = issue["id"]

        # Workspace activity
        activity = await client.list_workspace_activity(ws_id)
        assert len(activity) >= 1

        # Issue-specific activity
        issue_activity = await client.list_issue_activity(ws_id, issue_id)
        assert len(issue_activity) >= 1

        # Pagination
        paged = await client.list_workspace_activity(ws_id, limit=1, offset=0)
        assert len(paged) <= 1


# ── Connection Pooling ────────────────────────────────────────────────────

class TestClientConnectionPooling:
    @pytest.mark.asyncio
    async def test_context_manager(self, app):
        """Test that PlatformClient works as async context manager with pooling."""
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            pc = PlatformClient(base_url="http://test")
            pc._client = http
            pc._owned_client = True

            await pc.register("pool@test.com", "pass123")
            ws = await pc.create_workspace("PoolWS")
            assert ws["name"] == "PoolWS"

    @pytest.mark.asyncio
    async def test_standalone_mode(self, app):
        """Test that standalone (no context manager) mode still works."""
        pc = PlatformClient(base_url="http://test")
        assert pc._client is None
        assert pc._owned_client is False


# ── RBAC Enforcement ──────────────────────────────────────────────────────

class TestRBACEnforcement:
    @pytest.mark.asyncio
    async def test_non_member_gets_403(self, client: PlatformClient):
        """A user who is not a workspace member should get 403."""
        # User 1 creates workspace
        await client.register("owner@rbac.com", "pass123")
        ws = await client.create_workspace("RBACTest")
        ws_id = ws["id"]

        # User 2 registers (not added to workspace)
        await client.register("outsider@rbac.com", "pass123")

        # User 2 tries to access workspace — should fail
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await client.get_workspace(ws_id)
        assert exc_info.value.response.status_code == 403

    @pytest.mark.asyncio
    async def test_member_can_access(self, client: PlatformClient):
        """A workspace member should be able to access resources."""
        await client.register("member_owner@rbac.com", "pass123")
        ws = await client.create_workspace("MemberAccess")
        ws_id = ws["id"]

        # Owner can access
        got = await client.get_workspace(ws_id)
        assert got["id"] == ws_id

        # Create a project too
        proj = await client.create_project(ws_id, "Accessible Project")
        assert proj["title"] == "Accessible Project"
