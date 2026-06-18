"""Cross-workspace validation for issue body references (GHSA-2fjj)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from praisonai_platform.api.deps import validate_issue_refs_in_workspace
from praisonai_platform.services.agent_service import AgentService
from praisonai_platform.services.auth_service import AuthService
from praisonai_platform.services.issue_service import IssueService
from praisonai_platform.services.project_service import ProjectService
from praisonai_platform.services.workspace_service import WorkspaceService


@pytest.mark.asyncio
async def test_reject_foreign_project_on_create(session):
    auth = AuthService(session)
    user, _ = await auth.register("refs@test.com", "pass")
    ws_a = await WorkspaceService(session).create("A", user.id)
    ws_b = await WorkspaceService(session).create("B", user.id)
    foreign = await ProjectService(session).create(ws_b.id, "foreign")

    with pytest.raises(HTTPException) as exc:
        await validate_issue_refs_in_workspace(
            ws_a.id, session, project_id=foreign.id
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_reject_foreign_parent_issue(session):
    auth = AuthService(session)
    user, _ = await auth.register("parent@test.com", "pass")
    ws_a = await WorkspaceService(session).create("A", user.id)
    ws_b = await WorkspaceService(session).create("B", user.id)
    parent = await IssueService(session).create(
        workspace_id=ws_b.id, title="parent", creator_id=user.id
    )

    with pytest.raises(HTTPException) as exc:
        await validate_issue_refs_in_workspace(
            ws_a.id, session, parent_issue_id=parent.id
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_stats_scoped_to_workspace(session):
    auth = AuthService(session)
    user, _ = await auth.register("stats_scope@test.com", "pass")
    ws_a = await WorkspaceService(session).create("A", user.id)
    ws_b = await WorkspaceService(session).create("B", user.id)
    proj_svc = ProjectService(session)
    issue_svc = IssueService(session)

    proj_a = await proj_svc.create(ws_a.id, "A project")
    proj_b = await proj_svc.create(ws_b.id, "B project")
    await issue_svc.create(ws_a.id, "in A", user.id, project_id=proj_a.id)
    await issue_svc.create(ws_b.id, "in B", user.id, project_id=proj_b.id)

    stats_a = await proj_svc.get_stats(proj_a.id, workspace_id=ws_a.id)
    assert stats_a["total"] == 1

    stats_b_view = await proj_svc.get_stats(proj_b.id, workspace_id=ws_a.id)
    assert stats_b_view["total"] == 0


@pytest.mark.asyncio
async def test_reject_foreign_agent_assignee(session):
    auth = AuthService(session)
    user, _ = await auth.register("agent_ref@test.com", "pass")
    ws_a = await WorkspaceService(session).create("A", user.id)
    ws_b = await WorkspaceService(session).create("B", user.id)
    agent = await AgentService(session).create(ws_b.id, "bot")

    with pytest.raises(HTTPException) as exc:
        await validate_issue_refs_in_workspace(
            ws_a.id,
            session,
            assignee_type="agent",
            assignee_id=agent.id,
        )
    assert exc.value.status_code == 404
