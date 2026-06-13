"""FastAPI dependency injection."""

from __future__ import annotations

from typing import AsyncGenerator, Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from praisonaiagents.auth import AuthIdentity

from ..db.base import get_session
from ..services.auth_service import AuthService
from ..services.member_service import MemberService


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session per request."""
    async for session in get_session():
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_current_user(
    authorization: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_db),
) -> AuthIdentity:
    """Extract and verify the current user from Authorization header."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Use: Bearer <token>",
        )
    auth_svc = AuthService(session)
    identity = await auth_svc.authenticate({"token": token})
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return identity


async def require_workspace_member(
    workspace_id: str,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    min_role: str = "member",
) -> AuthIdentity:
    """Verify the current user is a member of the workspace.

    Returns the AuthIdentity with workspace_id set.
    Raises 403 if the user is not a member or lacks the required role.
    """
    member_svc = MemberService(session)
    has = await member_svc.has_role(workspace_id, user.id, min_role)
    if not has:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this workspace or insufficient role",
        )
    user.workspace_id = workspace_id
    return user


async def require_workspace_admin(
    workspace_id: str,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AuthIdentity:
    """Require admin or owner role in the workspace."""
    return await require_workspace_member(
        workspace_id, user, session, min_role="admin"
    )


async def require_workspace_owner(
    workspace_id: str,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AuthIdentity:
    """Require owner role in the workspace."""
    return await require_workspace_member(
        workspace_id, user, session, min_role="owner"
    )


async def require_delete_permission(
    workspace_id: str,
    user: AuthIdentity,
    session: AsyncSession,
    *,
    resource_owner_id: Optional[str] = None,
) -> None:
    """Allow delete when user is admin/owner or owns the resource."""
    member_svc = MemberService(session)
    if await member_svc.has_role(workspace_id, user.id, "admin"):
        return
    if resource_owner_id and resource_owner_id == user.id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permission to delete this resource",
    )


def ensure_resource_in_workspace(
    resource_workspace_id: str | None,
    workspace_id: str,
    *,
    label: str = "Resource",
) -> None:
    """Reject cross-workspace access (IDOR) with a generic 404."""
    if resource_workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{label} not found",
        )


async def require_issue_in_workspace(
    workspace_id: str,
    issue_id: str,
    session: AsyncSession,
):
    """Load an issue and verify it belongs to the URL workspace."""
    from ..db.models import Issue

    issue = await session.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue not found",
        )
    ensure_resource_in_workspace(issue.workspace_id, workspace_id, label="Issue")
    return issue
