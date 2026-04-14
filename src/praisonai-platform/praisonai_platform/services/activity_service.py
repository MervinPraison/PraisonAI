"""Activity log service — audit trail for workspace actions."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import ActivityLog


class ActivityService:
    """Activity log operations."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def log(
        self,
        workspace_id: str,
        action: str,
        actor_type: Optional[str] = None,
        actor_id: Optional[str] = None,
        issue_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> ActivityLog:
        """Record an activity."""
        entry = ActivityLog(
            workspace_id=workspace_id,
            action=action,
            actor_type=actor_type,
            actor_id=actor_id,
            issue_id=issue_id,
            details=details or {},
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def list_for_workspace(
        self,
        workspace_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ActivityLog]:
        """List recent activity for a workspace."""
        stmt = (
            select(ActivityLog)
            .where(ActivityLog.workspace_id == workspace_id)
            .order_by(ActivityLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_issue(
        self,
        issue_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ActivityLog]:
        """List activity for a specific issue."""
        stmt = (
            select(ActivityLog)
            .where(ActivityLog.issue_id == issue_id)
            .order_by(ActivityLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
