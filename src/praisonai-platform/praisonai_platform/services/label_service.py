"""
Label service — CRUD for workspace issue labels and issue-label links.

Influenced by Multica's issue_label + issue_to_label schema.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import IssueLabel, IssueLabelLink


class LabelService:
    """Issue label CRUD operations."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        workspace_id: str,
        name: str,
        color: str = "#6B7280",
    ) -> IssueLabel:
        """Create a label in a workspace."""
        label = IssueLabel(workspace_id=workspace_id, name=name, color=color)
        self._session.add(label)
        await self._session.flush()
        return label

    async def get(self, label_id: str) -> Optional[IssueLabel]:
        """Get label by ID."""
        return await self._session.get(IssueLabel, label_id)

    async def list_for_workspace(self, workspace_id: str) -> list[IssueLabel]:
        """List all labels in a workspace."""
        stmt = select(IssueLabel).where(IssueLabel.workspace_id == workspace_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        label_id: str,
        name: Optional[str] = None,
        color: Optional[str] = None,
    ) -> Optional[IssueLabel]:
        """Update a label."""
        label = await self.get(label_id)
        if label is None:
            return None
        if name is not None:
            label.name = name
        if color is not None:
            label.color = color
        await self._session.flush()
        return label

    async def delete(self, label_id: str) -> bool:
        """Delete a label."""
        label = await self.get(label_id)
        if label is None:
            return False
        await self._session.delete(label)
        await self._session.flush()
        return True

    # ── Issue-Label linking ────────────────────────────────────────────────

    async def add_to_issue(self, issue_id: str, label_id: str) -> None:
        """Attach a label to an issue."""
        link = IssueLabelLink(issue_id=issue_id, label_id=label_id)
        self._session.add(link)
        await self._session.flush()

    async def remove_from_issue(self, issue_id: str, label_id: str) -> None:
        """Remove a label from an issue."""
        stmt = delete(IssueLabelLink).where(
            IssueLabelLink.issue_id == issue_id,
            IssueLabelLink.label_id == label_id,
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def list_for_issue(self, issue_id: str) -> list[IssueLabel]:
        """List all labels on an issue."""
        stmt = (
            select(IssueLabel)
            .join(IssueLabelLink, IssueLabelLink.label_id == IssueLabel.id)
            .where(IssueLabelLink.issue_id == issue_id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
