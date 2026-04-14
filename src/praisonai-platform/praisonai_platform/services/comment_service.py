"""Comment service — CRUD for issue comments."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Comment


class CommentService:
    """Comment CRUD operations."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        issue_id: str,
        author_id: str,
        content: str,
        author_type: str = "member",
        comment_type: str = "comment",
        parent_id: Optional[str] = None,
    ) -> Comment:
        """Add a comment to an issue."""
        comment = Comment(
            issue_id=issue_id,
            author_type=author_type,
            author_id=author_id,
            parent_id=parent_id,
            content=content,
            type=comment_type,
        )
        self._session.add(comment)
        await self._session.flush()
        return comment

    async def get(self, comment_id: str) -> Optional[Comment]:
        """Get comment by ID."""
        return await self._session.get(Comment, comment_id)

    async def list_for_issue(self, issue_id: str) -> list[Comment]:
        """List all comments on an issue."""
        stmt = (
            select(Comment)
            .where(Comment.issue_id == issue_id)
            .order_by(Comment.created_at)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update(self, comment_id: str, content: str) -> Optional[Comment]:
        """Update comment content."""
        comment = await self.get(comment_id)
        if comment is None:
            return None
        comment.content = content
        await self._session.flush()
        return comment

    async def delete(self, comment_id: str) -> bool:
        """Delete a comment."""
        comment = await self.get(comment_id)
        if comment is None:
            return False
        await self._session.delete(comment)
        await self._session.flush()
        return True
