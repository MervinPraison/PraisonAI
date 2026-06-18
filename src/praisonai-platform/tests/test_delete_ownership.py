"""DELETE ownership checks for platform resources."""

from __future__ import annotations

import pytest

from praisonai_platform.services.auth_service import AuthService
from praisonai_platform.services.issue_service import IssueService
from praisonai_platform.services.member_service import MemberService
from praisonai_platform.services.workspace_service import WorkspaceService
from praisonaiagents.auth import AuthIdentity

from praisonai_platform.api.deps import require_delete_permission


@pytest.mark.asyncio
async def test_member_cannot_delete_others_issue(session):
    auth = AuthService(session)
    owner, _ = await auth.register("owner@test.com", "pass")
    other_user, _ = await auth.register("other@test.com", "pass")
    ws = await WorkspaceService(session).create("Team", owner.id)
    await MemberService(session).add(ws.id, other_user.id, "member")

    issue = await IssueService(session).create(
        workspace_id=ws.id,
        title="private",
        creator_id=owner.id,
    )

    other = AuthIdentity(id=other_user.id, email=other_user.email, name=other_user.name)
    with pytest.raises(Exception) as exc:
        await require_delete_permission(
            ws.id, other, session, resource_owner_id=issue.creator_id
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_delete_any_issue(session):
    auth = AuthService(session)
    owner, _ = await auth.register("admin_owner@test.com", "pass")
    admin_user, _ = await auth.register("admin@test.com", "pass")
    ws = await WorkspaceService(session).create("AdminTeam", owner.id)
    await MemberService(session).add(ws.id, admin_user.id, "admin")

    issue = await IssueService(session).create(
        workspace_id=ws.id,
        title="shared",
        creator_id=owner.id,
    )

    admin = AuthIdentity(id=admin_user.id, email=admin_user.email, name=admin_user.name)
    await require_delete_permission(
        ws.id, admin, session, resource_owner_id=issue.creator_id
    )
