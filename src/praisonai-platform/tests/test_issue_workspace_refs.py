"""GHSA-2fjj-qqg8-fg7x: issue refs must belong to URL workspace."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from praisonai_platform.api.deps import validate_issue_refs_in_workspace
from praisonai_platform.services.agent_service import AgentService
from praisonai_platform.services.auth_service import AuthService
from praisonai_platform.services.issue_service import IssueService
from praisonai_platform.services.member_service import MemberService
from praisonai_platform.services.project_service import ProjectService
from praisonai_platform.services.workspace_service import WorkspaceService


@pytest.mark.asyncio
async def test_rejects_foreign_project_id(session):
    auth = AuthService(session)
    user, _ = await auth.register("ref_proj@test.com", "pass")
    ws_a = await WorkspaceService(session).create("A", user.id)
    ws_b = await WorkspaceService(session).create("B", user.id)
    foreign = await ProjectService(session).create(ws_b.id, "Foreign")

    with pytest.raises(HTTPException) as exc:
        await validate_issue_refs_in_workspace(
            ws_a.id, session, project_id=foreign.id
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_rejects_foreign_parent_issue_id(session):
    auth = AuthService(session)
    user, _ = await auth.register("ref_parent@test.com", "pass")
    ws_a = await WorkspaceService(session).create("A", user.id)
    ws_b = await WorkspaceService(session).create("B", user.id)
    foreign = await IssueService(session).create(
        workspace_id=ws_b.id, title="parent", creator_id=user.id
    )

    with pytest.raises(HTTPException) as exc:
        await validate_issue_refs_in_workspace(
            ws_a.id, session, parent_issue_id=foreign.id
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_rejects_foreign_member_assignee(session):
    auth = AuthService(session)
    owner, _ = await auth.register("ref_mem_owner@test.com", "pass")
    outsider, _ = await auth.register("ref_mem_out@test.com", "pass")
    ws = await WorkspaceService(session).create("Team", owner.id)

    with pytest.raises(HTTPException) as exc:
        await validate_issue_refs_in_workspace(
            ws.id,
            session,
            assignee_type="member",
            assignee_id=outsider.id,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_rejects_foreign_agent_assignee(session):
    auth = AuthService(session)
    user, _ = await auth.register("ref_agent@test.com", "pass")
    ws_a = await WorkspaceService(session).create("A", user.id)
    ws_b = await WorkspaceService(session).create("B", user.id)
    foreign = await AgentService(session).create(ws_b.id, "Bot")

    with pytest.raises(HTTPException) as exc:
        await validate_issue_refs_in_workspace(
            ws_a.id,
            session,
            assignee_type="agent",
            assignee_id=foreign.id,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_accepts_valid_workspace_refs(session):
    auth = AuthService(session)
    owner, _ = await auth.register("ref_ok@test.com", "pass")
    member_user, _ = await auth.register("ref_member@test.com", "pass")
    ws = await WorkspaceService(session).create("Team", owner.id)
    await MemberService(session).add(ws.id, member_user.id, "member")
    project = await ProjectService(session).create(ws.id, "P1")
    parent = await IssueService(session).create(
        workspace_id=ws.id, title="parent", creator_id=owner.id
    )
    agent = await AgentService(session).create(ws.id, "Bot")

    await validate_issue_refs_in_workspace(
        ws.id,
        session,
        project_id=project.id,
        parent_issue_id=parent.id,
        assignee_type="member",
        assignee_id=member_user.id,
    )
    await validate_issue_refs_in_workspace(
        ws.id,
        session,
        assignee_type="agent",
        assignee_id=agent.id,
    )


@pytest.mark.asyncio
async def test_get_stats_scoped_to_workspace(session):
    auth = AuthService(session)
    user, _ = await auth.register("stats_scope@test.com", "pass")
    ws_a = await WorkspaceService(session).create("A", user.id)
    ws_b = await WorkspaceService(session).create("B", user.id)
    proj_svc = ProjectService(session)
    issue_svc = IssueService(session)
    project_a = await proj_svc.create(ws_a.id, "ProjA")
    project_b = await proj_svc.create(ws_b.id, "ProjB")

    await issue_svc.create(
        ws_a.id, "In A", user.id, project_id=project_a.id, status="todo"
    )
    # Simulate cross-workspace pollution (pre-fix behaviour)
    await issue_svc.create(
        ws_b.id, "Polluted", user.id, project_id=project_a.id, status="done"
    )
    await issue_svc.create(
        ws_b.id, "In B", user.id, project_id=project_b.id, status="todo"
    )

    stats_a = await proj_svc.get_stats(project_a.id, workspace_id=ws_a.id)
    assert stats_a["total"] == 1
    assert stats_a["by_status"]["todo"] == 1

    stats_b_on_a = await proj_svc.get_stats(project_a.id, workspace_id=ws_b.id)
    assert stats_b_on_a["total"] == 1
    assert stats_b_on_a["by_status"]["done"] == 1
