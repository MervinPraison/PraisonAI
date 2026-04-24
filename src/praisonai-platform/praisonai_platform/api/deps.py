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
