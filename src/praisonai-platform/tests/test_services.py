"""Unit tests for all platform services."""

import pytest

from praisonai_platform.services.auth_service import AuthService
from praisonai_platform.services.workspace_service import WorkspaceService
from praisonai_platform.services.member_service import MemberService
from praisonai_platform.services.project_service import ProjectService
from praisonai_platform.services.issue_service import IssueService
from praisonai_platform.services.comment_service import CommentService
from praisonai_platform.services.activity_service import ActivityService


# ── Auth Service ─────────────────────────────────────────────────────────────


class TestAuthService:
    @pytest.mark.asyncio
    async def test_register(self, session):
        svc = AuthService(session)
        user, token = await svc.register("alice@test.com", "password123", "Alice")
        assert user.email == "alice@test.com"
        assert user.name == "Alice"
        assert user.password_hash is not None
        assert token is not None
        assert len(token) > 20

    @pytest.mark.asyncio
    async def test_register_default_name(self, session):
        svc = AuthService(session)
        user, _ = await svc.register("bob@test.com", "pass")
        assert user.name == "bob"

    @pytest.mark.asyncio
    async def test_login_success(self, session):
        svc = AuthService(session)
        await svc.register("carol@test.com", "mypass", "Carol")
        result = await svc.login("carol@test.com", "mypass")
        assert result is not None
        user, token = result
        assert user.email == "carol@test.com"
        assert token is not None

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, session):
        svc = AuthService(session)
        await svc.register("dan@test.com", "correct")
        result = await svc.login("dan@test.com", "wrong")
        assert result is None

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, session):
        svc = AuthService(session)
        result = await svc.login("nobody@test.com", "pass")
        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_with_token(self, session):
        svc = AuthService(session)
        _, token = await svc.register("eve@test.com", "pass", "Eve")
        identity = await svc.authenticate({"token": token})
        assert identity is not None
        assert identity.email == "eve@test.com"
        assert identity.name == "Eve"

    @pytest.mark.asyncio
    async def test_authenticate_bad_token(self, session):
        svc = AuthService(session)
        identity = await svc.authenticate({"token": "invalid.jwt.token"})
        assert identity is None

    @pytest.mark.asyncio
    async def test_authenticate_with_credentials(self, session):
        svc = AuthService(session)
        await svc.register("frank@test.com", "pass123", "Frank")
        identity = await svc.authenticate({"email": "frank@test.com", "password": "pass123"})
        assert identity is not None
        assert identity.email == "frank@test.com"

    @pytest.mark.asyncio
    async def test_authorize(self, session):
        svc = AuthService(session)
        from praisonaiagents.auth import AuthIdentity
        identity = AuthIdentity(id="u-1", workspace_id="ws-1", roles=["owner"])
        # Without workspace member record, auth will check DB — returns False
        result = await svc.authorize(identity, "issue:1", "delete")
        assert result is False


# ── Workspace Service ────────────────────────────────────────────────────────


class TestWorkspaceService:
    @pytest.mark.asyncio
    async def test_create_workspace(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("ws_owner@test.com", "pass")
        svc = WorkspaceService(session)
        ws = await svc.create("My Workspace", user.id)
        assert ws.name == "My Workspace"
        assert ws.slug == "my-workspace"
        assert ws.id is not None

    @pytest.mark.asyncio
    async def test_create_workspace_custom_slug(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("ws_slug@test.com", "pass")
        svc = WorkspaceService(session)
        ws = await svc.create("Test", user.id, slug="custom-slug")
        assert ws.slug == "custom-slug"

    @pytest.mark.asyncio
    async def test_create_workspace_duplicate_slug(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("ws_dup@test.com", "pass")
        svc = WorkspaceService(session)
        ws1 = await svc.create("Same", user.id, slug="same")
        ws2 = await svc.create("Same", user.id, slug="same")
        assert ws1.slug == "same"
        assert ws2.slug == "same-1"

    @pytest.mark.asyncio
    async def test_get_workspace(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("ws_get@test.com", "pass")
        svc = WorkspaceService(session)
        ws = await svc.create("GetMe", user.id)
        fetched = await svc.get(ws.id)
        assert fetched is not None
        assert fetched.name == "GetMe"

    @pytest.mark.asyncio
    async def test_get_by_slug(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("ws_slug2@test.com", "pass")
        svc = WorkspaceService(session)
        ws = await svc.create("BySlug", user.id)
        fetched = await svc.get_by_slug(ws.slug)
        assert fetched is not None
        assert fetched.id == ws.id

    @pytest.mark.asyncio
    async def test_list_for_user(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("ws_list@test.com", "pass")
        svc = WorkspaceService(session)
        await svc.create("WS1", user.id)
        await svc.create("WS2", user.id)
        workspaces = await svc.list_for_user(user.id)
        assert len(workspaces) >= 2

    @pytest.mark.asyncio
    async def test_update_workspace(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("ws_upd@test.com", "pass")
        svc = WorkspaceService(session)
        ws = await svc.create("Original", user.id)
        updated = await svc.update(ws.id, name="Updated")
        assert updated.name == "Updated"

    @pytest.mark.asyncio
    async def test_delete_workspace(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("ws_del@test.com", "pass")
        svc = WorkspaceService(session)
        ws = await svc.create("ToDelete", user.id)
        assert await svc.delete(ws.id) is True
        assert await svc.get(ws.id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, session):
        svc = WorkspaceService(session)
        assert await svc.delete("nonexistent-id") is False


# ── Member Service ───────────────────────────────────────────────────────────


class TestMemberService:
    @pytest.mark.asyncio
    async def test_add_member(self, session):
        auth = AuthService(session)
        user1, _ = await auth.register("m_owner@test.com", "pass")
        user2, _ = await auth.register("m_member@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("MemberWS", user1.id)
        svc = MemberService(session)
        member = await svc.add(ws.id, user2.id, "member")
        assert member.role == "member"
        assert member.user_id == user2.id

    @pytest.mark.asyncio
    async def test_invalid_role(self, session):
        svc = MemberService(session)
        with pytest.raises(ValueError, match="Invalid role"):
            await svc.add("ws-1", "u-1", "superadmin")

    @pytest.mark.asyncio
    async def test_list_members(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("m_list@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("ListMembersWS", user.id)
        svc = MemberService(session)
        members = await svc.list_members(ws.id)
        assert len(members) >= 1  # owner auto-added

    @pytest.mark.asyncio
    async def test_update_role(self, session):
        auth = AuthService(session)
        user1, _ = await auth.register("m_role1@test.com", "pass")
        user2, _ = await auth.register("m_role2@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("RoleWS", user1.id)
        svc = MemberService(session)
        await svc.add(ws.id, user2.id, "member")
        updated = await svc.update_role(ws.id, user2.id, "admin")
        assert updated.role == "admin"

    @pytest.mark.asyncio
    async def test_remove_member(self, session):
        auth = AuthService(session)
        user1, _ = await auth.register("m_rem1@test.com", "pass")
        user2, _ = await auth.register("m_rem2@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("RemWS", user1.id)
        svc = MemberService(session)
        await svc.add(ws.id, user2.id, "member")
        assert await svc.remove(ws.id, user2.id) is True
        assert await svc.get(ws.id, user2.id) is None

    @pytest.mark.asyncio
    async def test_has_role(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("m_has@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("HasRoleWS", user.id)
        svc = MemberService(session)
        # Owner should have at least "member" access
        assert await svc.has_role(ws.id, user.id, "member") is True
        assert await svc.has_role(ws.id, user.id, "admin") is True
        assert await svc.has_role(ws.id, user.id, "owner") is True
        assert await svc.has_role(ws.id, "nonexistent", "member") is False


# ── Project Service ──────────────────────────────────────────────────────────


class TestProjectService:
    @pytest.mark.asyncio
    async def test_create_project(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("p_create@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("ProjectWS", user.id)
        svc = ProjectService(session)
        project = await svc.create(ws.id, "My Project", description="A project")
        assert project.title == "My Project"
        assert project.status == "planned"

    @pytest.mark.asyncio
    async def test_list_projects(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("p_list@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("ProjListWS", user.id)
        svc = ProjectService(session)
        await svc.create(ws.id, "P1")
        await svc.create(ws.id, "P2")
        projects = await svc.list_for_workspace(ws.id)
        assert len(projects) == 2

    @pytest.mark.asyncio
    async def test_update_project(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("p_upd@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("ProjUpdWS", user.id)
        svc = ProjectService(session)
        project = await svc.create(ws.id, "Original")
        updated = await svc.update(project.id, title="Updated", status="in_progress")
        assert updated.title == "Updated"
        assert updated.status == "in_progress"

    @pytest.mark.asyncio
    async def test_delete_project(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("p_del@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("ProjDelWS", user.id)
        svc = ProjectService(session)
        project = await svc.create(ws.id, "ToDelete")
        assert await svc.delete(project.id) is True
        assert await svc.get(project.id) is None

    @pytest.mark.asyncio
    async def test_get_stats(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("p_stats@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("ProjStatsWS", user.id)
        proj_svc = ProjectService(session)
        project = await proj_svc.create(ws.id, "StatsProj")
        issue_svc = IssueService(session)
        await issue_svc.create(ws.id, "Issue1", user.id, project_id=project.id, status="todo")
        await issue_svc.create(ws.id, "Issue2", user.id, project_id=project.id, status="todo")
        await issue_svc.create(ws.id, "Issue3", user.id, project_id=project.id, status="done")
        stats = await proj_svc.get_stats(project.id)
        assert stats["total"] == 3
        assert stats["by_status"]["todo"] == 2
        assert stats["by_status"]["done"] == 1


# ── Issue Service ────────────────────────────────────────────────────────────


class TestIssueService:
    @pytest.mark.asyncio
    async def test_create_issue(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("i_create@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("IssueWS", user.id)
        svc = IssueService(session)
        issue = await svc.create(ws.id, "Bug report", user.id)
        assert issue.title == "Bug report"
        assert issue.status == "backlog"
        assert issue.priority == "none"
        assert issue.creator_id == user.id

    @pytest.mark.asyncio
    async def test_create_issue_with_agent_creator(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("i_agent@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("AgentIssueWS", user.id)
        svc = IssueService(session)
        issue = await svc.create(ws.id, "Agent Task", "agent-1", creator_type="agent")
        assert issue.creator_type == "agent"
        assert issue.creator_id == "agent-1"

    @pytest.mark.asyncio
    async def test_list_issues_with_filters(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("i_filter@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("FilterWS", user.id)
        svc = IssueService(session)
        await svc.create(ws.id, "Todo1", user.id, status="todo")
        await svc.create(ws.id, "Done1", user.id, status="done")
        todo_issues = await svc.list_for_workspace(ws.id, status="todo")
        assert len(todo_issues) == 1
        assert todo_issues[0].title == "Todo1"

    @pytest.mark.asyncio
    async def test_assign_to_agent(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("i_assign@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("AssignWS", user.id)
        svc = IssueService(session)
        issue = await svc.create(ws.id, "To Assign", user.id)
        assigned = await svc.assign(issue.id, "agent", "agent-42")
        assert assigned.assignee_type == "agent"
        assert assigned.assignee_id == "agent-42"

    @pytest.mark.asyncio
    async def test_invalid_assignee_type(self, session):
        svc = IssueService(session)
        with pytest.raises(ValueError, match="Invalid assignee_type"):
            await svc.assign("issue-1", "robot", "r-1")

    @pytest.mark.asyncio
    async def test_transition(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("i_trans@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("TransWS", user.id)
        svc = IssueService(session)
        issue = await svc.create(ws.id, "Transition", user.id)
        assert issue.status == "backlog"
        updated = await svc.transition(issue.id, "in_progress")
        assert updated.status == "in_progress"

    @pytest.mark.asyncio
    async def test_invalid_status(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("i_badstat@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("BadStatWS", user.id)
        svc = IssueService(session)
        issue = await svc.create(ws.id, "BadStat", user.id)
        with pytest.raises(ValueError, match="Invalid status"):
            await svc.update(issue.id, status="invalid_status")

    @pytest.mark.asyncio
    async def test_sub_issues(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("i_sub@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("SubWS", user.id)
        svc = IssueService(session)
        parent = await svc.create(ws.id, "Parent Issue", user.id)
        child = await svc.create(ws.id, "Child Issue", user.id, parent_issue_id=parent.id)
        assert child.parent_issue_id == parent.id
        sub_issues = await svc.list_sub_issues(parent.id)
        assert len(sub_issues) == 1
        assert sub_issues[0].id == child.id

    @pytest.mark.asyncio
    async def test_delete_issue(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("i_del@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("DelIssueWS", user.id)
        svc = IssueService(session)
        issue = await svc.create(ws.id, "ToDelete", user.id)
        assert await svc.delete(issue.id) is True
        assert await svc.get(issue.id) is None


# ── Comment Service ──────────────────────────────────────────────────────────


class TestCommentService:
    @pytest.mark.asyncio
    async def test_create_comment(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("c_create@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("CommentWS", user.id)
        issue_svc = IssueService(session)
        issue = await issue_svc.create(ws.id, "Commentable", user.id)
        svc = CommentService(session)
        comment = await svc.create(issue.id, user.id, "This is a comment")
        assert comment.content == "This is a comment"
        assert comment.author_type == "member"

    @pytest.mark.asyncio
    async def test_agent_comment(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("c_agent@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("AgentCommentWS", user.id)
        issue_svc = IssueService(session)
        issue = await issue_svc.create(ws.id, "AgentComment", user.id)
        svc = CommentService(session)
        comment = await svc.create(issue.id, "agent-1", "Agent progress update", "agent", "progress_update")
        assert comment.author_type == "agent"
        assert comment.type == "progress_update"

    @pytest.mark.asyncio
    async def test_list_comments(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("c_list@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("ListCommentWS", user.id)
        issue_svc = IssueService(session)
        issue = await issue_svc.create(ws.id, "WithComments", user.id)
        svc = CommentService(session)
        await svc.create(issue.id, user.id, "First")
        await svc.create(issue.id, user.id, "Second")
        comments = await svc.list_for_issue(issue.id)
        assert len(comments) == 2

    @pytest.mark.asyncio
    async def test_update_comment(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("c_upd@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("UpdCommentWS", user.id)
        issue_svc = IssueService(session)
        issue = await issue_svc.create(ws.id, "UpdComment", user.id)
        svc = CommentService(session)
        comment = await svc.create(issue.id, user.id, "Original")
        updated = await svc.update(comment.id, "Updated content")
        assert updated.content == "Updated content"

    @pytest.mark.asyncio
    async def test_delete_comment(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("c_del@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("DelCommentWS", user.id)
        issue_svc = IssueService(session)
        issue = await issue_svc.create(ws.id, "DelComment", user.id)
        svc = CommentService(session)
        comment = await svc.create(issue.id, user.id, "ToDelete")
        assert await svc.delete(comment.id) is True
        assert await svc.get(comment.id) is None


# ── Activity Service ─────────────────────────────────────────────────────────


class TestActivityService:
    @pytest.mark.asyncio
    async def test_log_activity(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("a_log@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("ActivityWS", user.id)
        svc = ActivityService(session)
        entry = await svc.log(ws.id, "issue.created", "member", user.id, details={"title": "Bug"})
        assert entry.action == "issue.created"
        assert entry.details["title"] == "Bug"

    @pytest.mark.asyncio
    async def test_list_for_workspace(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("a_list@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("ActivityListWS", user.id)
        svc = ActivityService(session)
        await svc.log(ws.id, "workspace.created", "member", user.id)
        await svc.log(ws.id, "member.added", "member", user.id)
        activities = await svc.list_for_workspace(ws.id)
        assert len(activities) >= 2

    @pytest.mark.asyncio
    async def test_list_for_issue(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("a_issue@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("ActivityIssueWS", user.id)
        issue_svc = IssueService(session)
        issue = await issue_svc.create(ws.id, "Tracked", user.id)
        svc = ActivityService(session)
        await svc.log(ws.id, "issue.created", "member", user.id, issue_id=issue.id)
        activities = await svc.list_for_issue(issue.id)
        assert len(activities) == 1
