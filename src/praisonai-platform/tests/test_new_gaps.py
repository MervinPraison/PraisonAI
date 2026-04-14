"""Tests for all new gap implementations:
GAP-1: Agent CRUD service
GAP-2: Label service + issue linking
GAP-3: Dependency service
GAP-4: Human-readable issue IDs
GAP-5: Threaded comments (parent_id)
GAP-6: Pagination
GAP-10: Agent instructions field
"""

import pytest

from praisonai_platform.services.auth_service import AuthService
from praisonai_platform.services.workspace_service import WorkspaceService
from praisonai_platform.services.issue_service import IssueService
from praisonai_platform.services.agent_service import AgentService
from praisonai_platform.services.label_service import LabelService
from praisonai_platform.services.dependency_service import DependencyService
from praisonai_platform.services.comment_service import CommentService
from praisonai_platform.services.activity_service import ActivityService


# ── Helpers ──────────────────────────────────────────────────────────────

async def _create_user_and_workspace(session, email="test@test.com"):
    auth = AuthService(session)
    user, _ = await auth.register(email, "pass")
    ws_svc = WorkspaceService(session)
    ws = await ws_svc.create("TestWS", user.id)
    return user, ws


# ── GAP-1: Agent CRUD ────────────────────────────────────────────────────


class TestAgentService:
    @pytest.mark.asyncio
    async def test_create_agent(self, session):
        user, ws = await _create_user_and_workspace(session, "ag_create@test.com")
        svc = AgentService(session)
        agent = await svc.create(ws.id, "CodeBot", owner_id=user.id)
        assert agent.name == "CodeBot"
        assert agent.status == "offline"
        assert agent.workspace_id == ws.id
        assert agent.owner_id == user.id

    @pytest.mark.asyncio
    async def test_create_agent_with_instructions(self, session):
        user, ws = await _create_user_and_workspace(session, "ag_instr@test.com")
        svc = AgentService(session)
        agent = await svc.create(ws.id, "InstrBot", instructions="You are a helpful bot.")
        assert agent.instructions == "You are a helpful bot."

    @pytest.mark.asyncio
    async def test_list_agents(self, session):
        user, ws = await _create_user_and_workspace(session, "ag_list@test.com")
        svc = AgentService(session)
        await svc.create(ws.id, "Agent1")
        await svc.create(ws.id, "Agent2")
        agents = await svc.list_for_workspace(ws.id)
        assert len(agents) == 2

    @pytest.mark.asyncio
    async def test_list_agents_filter_status(self, session):
        user, ws = await _create_user_and_workspace(session, "ag_filter@test.com")
        svc = AgentService(session)
        await svc.create(ws.id, "Active", status="idle")
        await svc.create(ws.id, "Off", status="offline")
        idle = await svc.list_for_workspace(ws.id, status="idle")
        assert len(idle) == 1
        assert idle[0].name == "Active"

    @pytest.mark.asyncio
    async def test_update_agent(self, session):
        user, ws = await _create_user_and_workspace(session, "ag_upd@test.com")
        svc = AgentService(session)
        agent = await svc.create(ws.id, "OldName")
        updated = await svc.update(agent.id, name="NewName", status="idle")
        assert updated.name == "NewName"
        assert updated.status == "idle"

    @pytest.mark.asyncio
    async def test_update_agent_invalid_status(self, session):
        user, ws = await _create_user_and_workspace(session, "ag_badstat@test.com")
        svc = AgentService(session)
        agent = await svc.create(ws.id, "Bot")
        with pytest.raises(ValueError, match="Invalid status"):
            await svc.update(agent.id, status="flying")

    @pytest.mark.asyncio
    async def test_delete_agent(self, session):
        user, ws = await _create_user_and_workspace(session, "ag_del@test.com")
        svc = AgentService(session)
        agent = await svc.create(ws.id, "ToDelete")
        assert await svc.delete(agent.id) is True
        assert await svc.get(agent.id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, session):
        svc = AgentService(session)
        assert await svc.delete("nonexistent") is False


# ── GAP-2: Label CRUD + Issue linking ─────────────────────────────────────


class TestLabelService:
    @pytest.mark.asyncio
    async def test_create_label(self, session):
        user, ws = await _create_user_and_workspace(session, "lbl_create@test.com")
        svc = LabelService(session)
        label = await svc.create(ws.id, "bug", "#FF0000")
        assert label.name == "bug"
        assert label.color == "#FF0000"

    @pytest.mark.asyncio
    async def test_list_labels(self, session):
        user, ws = await _create_user_and_workspace(session, "lbl_list@test.com")
        svc = LabelService(session)
        await svc.create(ws.id, "bug")
        await svc.create(ws.id, "feature")
        labels = await svc.list_for_workspace(ws.id)
        assert len(labels) == 2

    @pytest.mark.asyncio
    async def test_update_label(self, session):
        user, ws = await _create_user_and_workspace(session, "lbl_upd@test.com")
        svc = LabelService(session)
        label = await svc.create(ws.id, "old")
        updated = await svc.update(label.id, name="new", color="#00FF00")
        assert updated.name == "new"
        assert updated.color == "#00FF00"

    @pytest.mark.asyncio
    async def test_delete_label(self, session):
        user, ws = await _create_user_and_workspace(session, "lbl_del@test.com")
        svc = LabelService(session)
        label = await svc.create(ws.id, "gone")
        assert await svc.delete(label.id) is True
        assert await svc.get(label.id) is None

    @pytest.mark.asyncio
    async def test_add_remove_label_to_issue(self, session):
        user, ws = await _create_user_and_workspace(session, "lbl_link@test.com")
        label_svc = LabelService(session)
        issue_svc = IssueService(session)
        label = await label_svc.create(ws.id, "bug")
        issue = await issue_svc.create(ws.id, "Labeled Issue", user.id)
        await label_svc.add_to_issue(issue.id, label.id)
        labels = await label_svc.list_for_issue(issue.id)
        assert len(labels) == 1
        assert labels[0].id == label.id
        await label_svc.remove_from_issue(issue.id, label.id)
        labels2 = await label_svc.list_for_issue(issue.id)
        assert len(labels2) == 0


# ── GAP-3: Dependency service ─────────────────────────────────────────────


class TestDependencyService:
    @pytest.mark.asyncio
    async def test_create_dependency(self, session):
        user, ws = await _create_user_and_workspace(session, "dep_create@test.com")
        issue_svc = IssueService(session)
        i1 = await issue_svc.create(ws.id, "Blocker", user.id)
        i2 = await issue_svc.create(ws.id, "Blocked", user.id)
        dep_svc = DependencyService(session)
        dep = await dep_svc.create(i1.id, i2.id, "blocks")
        assert dep.issue_id == i1.id
        assert dep.depends_on_issue_id == i2.id
        assert dep.type == "blocks"

    @pytest.mark.asyncio
    async def test_invalid_dep_type(self, session):
        dep_svc = DependencyService(session)
        with pytest.raises(ValueError, match="Invalid type"):
            await dep_svc.create("a", "b", "depends_on")

    @pytest.mark.asyncio
    async def test_list_dependencies(self, session):
        user, ws = await _create_user_and_workspace(session, "dep_list@test.com")
        issue_svc = IssueService(session)
        i1 = await issue_svc.create(ws.id, "A", user.id)
        i2 = await issue_svc.create(ws.id, "B", user.id)
        dep_svc = DependencyService(session)
        await dep_svc.create(i1.id, i2.id, "blocks")
        deps_from_i1 = await dep_svc.list_for_issue(i1.id)
        deps_from_i2 = await dep_svc.list_for_issue(i2.id)
        assert len(deps_from_i1) == 1
        assert len(deps_from_i2) == 1  # Same dep shows from both sides

    @pytest.mark.asyncio
    async def test_delete_dependency(self, session):
        user, ws = await _create_user_and_workspace(session, "dep_del@test.com")
        issue_svc = IssueService(session)
        i1 = await issue_svc.create(ws.id, "X", user.id)
        i2 = await issue_svc.create(ws.id, "Y", user.id)
        dep_svc = DependencyService(session)
        dep = await dep_svc.create(i1.id, i2.id, "related")
        assert await dep_svc.delete(dep.id) is True
        assert await dep_svc.get(dep.id) is None


# ── GAP-4: Human-readable issue IDs ──────────────────────────────────────


class TestIssueNumbering:
    @pytest.mark.asyncio
    async def test_issue_auto_number(self, session):
        user, ws = await _create_user_and_workspace(session, "inum_auto@test.com")
        svc = IssueService(session)
        i1 = await svc.create(ws.id, "First", user.id)
        i2 = await svc.create(ws.id, "Second", user.id)
        assert i1.number == 1
        assert i1.identifier == "ISS-1"
        assert i2.number == 2
        assert i2.identifier == "ISS-2"

    @pytest.mark.asyncio
    async def test_custom_issue_prefix(self, session):
        auth = AuthService(session)
        user, _ = await auth.register("inum_prefix@test.com", "pass")
        ws_svc = WorkspaceService(session)
        ws = await ws_svc.create("PrefixWS", user.id)
        await ws_svc.update(ws.id, settings={"custom": True})
        # Directly update prefix for testing
        from praisonai_platform.db.models import Workspace
        ws_obj = await session.get(Workspace, ws.id)
        ws_obj.issue_prefix = "PRJ"
        await session.flush()
        svc = IssueService(session)
        issue = await svc.create(ws.id, "Custom Prefix", user.id)
        assert issue.identifier == "PRJ-1"

    @pytest.mark.asyncio
    async def test_counter_persists_across_creates(self, session):
        user, ws = await _create_user_and_workspace(session, "inum_persist@test.com")
        svc = IssueService(session)
        for i in range(5):
            issue = await svc.create(ws.id, f"Issue-{i}", user.id)
        assert issue.number == 5
        assert issue.identifier == "ISS-5"


# ── GAP-5: Threaded comments ─────────────────────────────────────────────


class TestThreadedComments:
    @pytest.mark.asyncio
    async def test_reply_to_comment(self, session):
        user, ws = await _create_user_and_workspace(session, "thread_reply@test.com")
        issue_svc = IssueService(session)
        issue = await issue_svc.create(ws.id, "ThreadIssue", user.id)
        svc = CommentService(session)
        parent = await svc.create(issue.id, user.id, "Parent comment")
        reply = await svc.create(issue.id, user.id, "Reply", parent_id=parent.id)
        assert reply.parent_id == parent.id

    @pytest.mark.asyncio
    async def test_top_level_comment_no_parent(self, session):
        user, ws = await _create_user_and_workspace(session, "thread_top@test.com")
        issue_svc = IssueService(session)
        issue = await issue_svc.create(ws.id, "TopIssue", user.id)
        svc = CommentService(session)
        comment = await svc.create(issue.id, user.id, "Top level")
        assert comment.parent_id is None


# ── GAP-6: Pagination ────────────────────────────────────────────────────


class TestPagination:
    @pytest.mark.asyncio
    async def test_issue_pagination(self, session):
        user, ws = await _create_user_and_workspace(session, "pag_issue@test.com")
        svc = IssueService(session)
        for i in range(10):
            await svc.create(ws.id, f"Issue {i}", user.id)
        page1 = await svc.list_for_workspace(ws.id, limit=3, offset=0)
        page2 = await svc.list_for_workspace(ws.id, limit=3, offset=3)
        assert len(page1) == 3
        assert len(page2) == 3
        assert page1[0].id != page2[0].id

    @pytest.mark.asyncio
    async def test_agent_pagination(self, session):
        user, ws = await _create_user_and_workspace(session, "pag_agent@test.com")
        svc = AgentService(session)
        for i in range(5):
            await svc.create(ws.id, f"Agent-{i}")
        page = await svc.list_for_workspace(ws.id, limit=2, offset=0)
        assert len(page) == 2

    @pytest.mark.asyncio
    async def test_activity_pagination(self, session):
        user, ws = await _create_user_and_workspace(session, "pag_act@test.com")
        svc = ActivityService(session)
        for i in range(5):
            await svc.log(ws.id, f"action.{i}", "member", user.id)
        page = await svc.list_for_workspace(ws.id, limit=2, offset=0)
        assert len(page) == 2


# ── GAP-10: Agent instructions in model ──────────────────────────────────


class TestAgentInstructions:
    @pytest.mark.asyncio
    async def test_instructions_persist(self, session):
        user, ws = await _create_user_and_workspace(session, "ag_instr2@test.com")
        svc = AgentService(session)
        agent = await svc.create(ws.id, "InstrBot", instructions="Do X then Y")
        fetched = await svc.get(agent.id)
        assert fetched.instructions == "Do X then Y"

    @pytest.mark.asyncio
    async def test_update_instructions(self, session):
        user, ws = await _create_user_and_workspace(session, "ag_instr3@test.com")
        svc = AgentService(session)
        agent = await svc.create(ws.id, "UpdInstr")
        updated = await svc.update(agent.id, instructions="New instructions")
        assert updated.instructions == "New instructions"
