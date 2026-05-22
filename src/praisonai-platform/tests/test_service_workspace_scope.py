"""Service-layer workspace scoping for issues and projects."""

from __future__ import annotations

import pytest

from praisonai_platform.services.auth_service import AuthService
from praisonai_platform.services.issue_service import IssueService
from praisonai_platform.services.project_service import ProjectService
from praisonai_platform.services.workspace_service import WorkspaceService


@pytest.mark.asyncio
async def test_issue_get_rejects_wrong_workspace(session):
    auth = AuthService(session)
    user, _ = await auth.register("scope@test.com", "pass")
    ws_a = await WorkspaceService(session).create("A", user.id)
    ws_b = await WorkspaceService(session).create("B", user.id)
    issue_svc = IssueService(session)
    issue = await issue_svc.create(
        workspace_id=ws_a.id,
        title="secret",
        creator_id=user.id,
    )
    assert await issue_svc.get(issue.id, workspace_id=ws_a.id) is not None
    assert await issue_svc.get(issue.id, workspace_id=ws_b.id) is None


@pytest.mark.asyncio
async def test_project_delete_scoped_to_workspace(session):
    auth = AuthService(session)
    user, _ = await auth.register("proj_scope@test.com", "pass")
    ws_a = await WorkspaceService(session).create("PA", user.id)
    ws_b = await WorkspaceService(session).create("PB", user.id)
    proj_svc = ProjectService(session)
    project = await proj_svc.create(workspace_id=ws_a.id, title="p1")
    assert await proj_svc.delete(project.id, workspace_id=ws_b.id) is False
    assert await proj_svc.delete(project.id, workspace_id=ws_a.id) is True
