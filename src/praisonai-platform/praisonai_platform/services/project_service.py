"""
Project service — CRUD with lead and issue linking.

Influenced by Multica's 034_projects.up.sql and project handler.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Issue, Project


class ProjectService:
    """Project CRUD operations."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        workspace_id: str,
        title: str,
        description: Optional[str] = None,
        icon: Optional[str] = None,
        status: str = "planned",
        lead_type: Optional[str] = None,
        lead_id: Optional[str] = None,
    ) -> Project:
        """Create a project."""
        project = Project(
            workspace_id=workspace_id,
            title=title,
            description=description,
            icon=icon,
            status=status,
            lead_type=lead_type,
            lead_id=lead_id,
        )
        self._session.add(project)
        await self._session.flush()
        return project

    async def get(self, project_id: str) -> Optional[Project]:
        """Get project by ID."""
        return await self._session.get(Project, project_id)

    async def list_for_workspace(
        self,
        workspace_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Project]:
        """List all projects in a workspace."""
        stmt = select(Project).where(Project.workspace_id == workspace_id).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        project_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        lead_type: Optional[str] = None,
        lead_id: Optional[str] = None,
    ) -> Optional[Project]:
        """Update project fields."""
        project = await self.get(project_id)
        if project is None:
            return None
        if title is not None:
            project.title = title
        if description is not None:
            project.description = description
        if status is not None:
            project.status = status
        if lead_type is not None:
            project.lead_type = lead_type
        if lead_id is not None:
            project.lead_id = lead_id
        await self._session.flush()
        return project

    async def delete(self, project_id: str) -> bool:
        """Delete a project."""
        project = await self.get(project_id)
        if project is None:
            return False
        await self._session.delete(project)
        await self._session.flush()
        return True

    async def get_stats(self, project_id: str) -> dict:
        """Get issue statistics for a project."""
        stmt = (
            select(Issue.status, func.count(Issue.id))
            .where(Issue.project_id == project_id)
            .group_by(Issue.status)
        )
        result = await self._session.execute(stmt)
        stats = {row[0]: row[1] for row in result.all()}
        total = sum(stats.values())
        return {"total": total, "by_status": stats}
