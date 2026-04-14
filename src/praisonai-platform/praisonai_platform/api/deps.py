"""FastAPI dependency injection."""

from __future__ import annotations

from typing import AsyncGenerator, Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from praisonaiagents.auth import AuthIdentity

# from ..db.base import get_session  # Commented out - missing db module
from ..services.auth_service import AuthService
from ..services.member_service import MemberService


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session per request."""
    # NOTE: This is a placeholder since db.base module is missing
    # In a real implementation, this would create a proper database session
    raise NotImplementedError("Database module not available")


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
    min_role: str = "member",
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AuthIdentity:
    """Require the current user to be a member of the specified workspace."""
    member_svc = MemberService(session)
    has_access = await member_svc.has_role(workspace_id, user.id, min_role)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You must be a workspace member to access this resource.",
        )
    # Set workspace_id on the identity for convenience
    user.workspace_id = workspace_id
    return user
