"""
Issue dependency service — manage issue relationships.

Influenced by Multica's issue_dependency (blocks/blocked_by/related)
and Paperclip's issue_relations.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import IssueDependency

VALID_TYPES = {"blocks", "blocked_by", "related"}


class DependencyService:
    """Issue dependency CRUD operations."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        issue_id: str,
        depends_on_issue_id: str,
        dep_type: str = "blocks",
    ) -> IssueDependency:
        """Create a dependency between two issues."""
        if dep_type not in VALID_TYPES:
            raise ValueError(f"Invalid type: {dep_type}. Must be one of {VALID_TYPES}")
        dep = IssueDependency(
            issue_id=issue_id,
            depends_on_issue_id=depends_on_issue_id,
            type=dep_type,
        )
        self._session.add(dep)
        await self._session.flush()
        return dep

    async def get(self, dep_id: str) -> Optional[IssueDependency]:
        """Get dependency by ID."""
        return await self._session.get(IssueDependency, dep_id)

    async def list_for_issue(self, issue_id: str) -> list[IssueDependency]:
        """List all dependencies for an issue (both directions)."""
        stmt = select(IssueDependency).where(
            (IssueDependency.issue_id == issue_id)
            | (IssueDependency.depends_on_issue_id == issue_id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete(self, dep_id: str) -> bool:
        """Delete a dependency."""
        dep = await self.get(dep_id)
        if dep is None:
            return False
        await self._session.delete(dep)
        await self._session.flush()
        return True
