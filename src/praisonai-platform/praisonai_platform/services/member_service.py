"""
Member/RBAC service.

Influenced by Multica's member handler (owner/admin/member roles)
and Paperclip's access service.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Member

VALID_ROLES = {"owner", "admin", "member"}


class MemberService:
    """Member management with role-based access control."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(
        self,
        workspace_id: str,
        user_id: str,
        role: str = "member",
    ) -> Member:
        """Add a user to a workspace."""
        if role not in VALID_ROLES:
            raise ValueError(f"Invalid role: {role}. Must be one of {VALID_ROLES}")
        member = Member(workspace_id=workspace_id, user_id=user_id, role=role)
        self._session.add(member)
        await self._session.flush()
        return member

    async def get(self, workspace_id: str, user_id: str) -> Optional[Member]:
        """Get a member by workspace + user."""
        stmt = select(Member).where(
            Member.workspace_id == workspace_id,
            Member.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_members(self, workspace_id: str) -> list[Member]:
        """List all members of a workspace."""
        stmt = select(Member).where(Member.workspace_id == workspace_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_role(
        self,
        workspace_id: str,
        user_id: str,
        new_role: str,
    ) -> Optional[Member]:
        """Update a member's role."""
        if new_role not in VALID_ROLES:
            raise ValueError(f"Invalid role: {new_role}. Must be one of {VALID_ROLES}")
        member = await self.get(workspace_id, user_id)
        if member is None:
            return None
        member.role = new_role
        await self._session.flush()
        return member

    async def remove(self, workspace_id: str, user_id: str) -> bool:
        """Remove a member from a workspace."""
        member = await self.get(workspace_id, user_id)
        if member is None:
            return False
        await self._session.delete(member)
        await self._session.flush()
        return True

    async def has_role(
        self,
        workspace_id: str,
        user_id: str,
        required_role: str,
    ) -> bool:
        """Check if a user has at least the required role.

        Role hierarchy: owner > admin > member.
        """
        member = await self.get(workspace_id, user_id)
        if member is None:
            return False
        role_levels = {"owner": 3, "admin": 2, "member": 1}
        user_level = role_levels.get(member.role, 0)
        required_level = role_levels.get(required_role, 0)
        return user_level >= required_level
