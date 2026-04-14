"""
Workspace service — CRUD with slug validation.

Influenced by Multica's workspace handler (CreateWorkspace, slug pattern)
and Paperclip's company service.
"""

from __future__ import annotations

import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Member, Workspace


def _slugify(name: str) -> str:
    """Convert name to a URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "workspace"


class WorkspaceService:
    """Workspace CRUD operations."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        name: str,
        owner_id: str,
        slug: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Workspace:
        """Create a workspace and add the creator as owner."""
        final_slug = slug or _slugify(name)
        final_slug = await self._ensure_unique_slug(final_slug)

        ws = Workspace(name=name, slug=final_slug, description=description)
        self._session.add(ws)
        await self._session.flush()

        member = Member(workspace_id=ws.id, user_id=owner_id, role="owner")
        self._session.add(member)
        await self._session.flush()
        return ws

    async def get(self, workspace_id: str) -> Optional[Workspace]:
        """Get workspace by ID."""
        return await self._session.get(Workspace, workspace_id)

    async def get_by_slug(self, slug: str) -> Optional[Workspace]:
        """Get workspace by slug."""
        stmt = select(Workspace).where(Workspace.slug == slug)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Workspace]:
        """List workspaces a user is a member of."""
        stmt = (
            select(Workspace)
            .join(Member, Member.workspace_id == Workspace.id)
            .where(Member.user_id == user_id)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        workspace_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        settings: Optional[dict] = None,
    ) -> Optional[Workspace]:
        """Update workspace fields."""
        ws = await self.get(workspace_id)
        if ws is None:
            return None
        if name is not None:
            ws.name = name
        if description is not None:
            ws.description = description
        if settings is not None:
            ws.settings = settings
        await self._session.flush()
        return ws

    async def delete(self, workspace_id: str) -> bool:
        """Delete a workspace."""
        ws = await self.get(workspace_id)
        if ws is None:
            return False
        await self._session.delete(ws)
        await self._session.flush()
        return True

    async def _ensure_unique_slug(self, slug: str) -> str:
        """Append a suffix if the slug is already taken."""
        base = slug
        counter = 1
        while True:
            stmt = select(Workspace.id).where(Workspace.slug == slug)
            result = await self._session.execute(stmt)
            if result.scalar_one_or_none() is None:
                return slug
            slug = f"{base}-{counter}"
            counter += 1
