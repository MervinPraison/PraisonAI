"""
Issue service — CRUD, status workflow, assignment, sub-issues.

Influenced by Multica's issue handler with status state machine,
agent assignment (assignee_type: member|agent), and sub-issues.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Issue, Workspace

VALID_STATUSES = {"backlog", "todo", "in_progress", "in_review", "done", "blocked", "cancelled"}
VALID_PRIORITIES = {"urgent", "high", "medium", "low", "none"}
VALID_ASSIGNEE_TYPES = {"member", "agent"}


class IssueService:
    """Issue management with status workflow."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        workspace_id: str,
        title: str,
        creator_id: str,
        creator_type: str = "member",
        project_id: Optional[str] = None,
        description: Optional[str] = None,
        status: str = "backlog",
        priority: str = "none",
        assignee_type: Optional[str] = None,
        assignee_id: Optional[str] = None,
        parent_issue_id: Optional[str] = None,
        acceptance_criteria: Optional[list] = None,
    ) -> Issue:
        """Create an issue with auto-assigned number and identifier."""
        ws = await self._session.get(Workspace, workspace_id)
        number = None
        identifier = None
        if ws is not None:
            ws.issue_counter = (ws.issue_counter or 0) + 1
            number = ws.issue_counter
            identifier = f"{ws.issue_prefix}-{number}"

        issue = Issue(
            workspace_id=workspace_id,
            project_id=project_id,
            title=title,
            description=description,
            status=status,
            priority=priority,
            assignee_type=assignee_type,
            assignee_id=assignee_id,
            creator_type=creator_type,
            creator_id=creator_id,
            parent_issue_id=parent_issue_id,
            acceptance_criteria=acceptance_criteria or [],
            number=number,
            identifier=identifier,
        )
        self._session.add(issue)
        await self._session.flush()
        return issue

    async def get(self, issue_id: str) -> Optional[Issue]:
        """Get issue by ID."""
        return await self._session.get(Issue, issue_id)

    async def list_for_workspace(
        self,
        workspace_id: str,
        status: Optional[str] = None,
        project_id: Optional[str] = None,
        assignee_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Issue]:
        """List issues with optional filters."""
        stmt = select(Issue).where(Issue.workspace_id == workspace_id)
        if status:
            stmt = stmt.where(Issue.status == status)
        if project_id:
            stmt = stmt.where(Issue.project_id == project_id)
        if assignee_id:
            stmt = stmt.where(Issue.assignee_id == assignee_id)
        stmt = stmt.order_by(Issue.position, Issue.created_at).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        issue_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        assignee_type: Optional[str] = None,
        assignee_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Optional[Issue]:
        """Update issue fields."""
        issue = await self.get(issue_id)
        if issue is None:
            return None
        if title is not None:
            issue.title = title
        if description is not None:
            issue.description = description
        if status is not None:
            if status not in VALID_STATUSES:
                raise ValueError(f"Invalid status: {status}")
            issue.status = status
        if priority is not None:
            if priority not in VALID_PRIORITIES:
                raise ValueError(f"Invalid priority: {priority}")
            issue.priority = priority
        if assignee_type is not None:
            issue.assignee_type = assignee_type
        if assignee_id is not None:
            issue.assignee_id = assignee_id
        if project_id is not None:
            issue.project_id = project_id
        await self._session.flush()
        return issue

    async def assign(
        self,
        issue_id: str,
        assignee_type: str,
        assignee_id: str,
    ) -> Optional[Issue]:
        """Assign an issue to a member or agent."""
        if assignee_type not in VALID_ASSIGNEE_TYPES:
            raise ValueError(f"Invalid assignee_type: {assignee_type}")
        return await self.update(
            issue_id, assignee_type=assignee_type, assignee_id=assignee_id
        )

    async def transition(self, issue_id: str, new_status: str) -> Optional[Issue]:
        """Transition an issue to a new status."""
        return await self.update(issue_id, status=new_status)

    async def delete(self, issue_id: str) -> bool:
        """Delete an issue."""
        issue = await self.get(issue_id)
        if issue is None:
            return False
        await self._session.delete(issue)
        await self._session.flush()
        return True

    async def list_sub_issues(self, parent_id: str) -> list[Issue]:
        """List sub-issues of a parent issue."""
        stmt = select(Issue).where(Issue.parent_issue_id == parent_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
