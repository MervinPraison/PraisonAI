"""
Agent service — CRUD for workspace agents.

Influenced by Multica's agent table (001_init + 021_instructions)
and Paperclip's agents schema (adapter, status, runtime config).
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Agent

VALID_STATUSES = {"idle", "working", "blocked", "error", "offline"}
VALID_RUNTIME_MODES = {"local", "cloud"}


class AgentService:
    """Agent CRUD operations."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        workspace_id: str,
        name: str,
        owner_id: Optional[str] = None,
        runtime_mode: str = "local",
        runtime_config: Optional[dict] = None,
        instructions: Optional[str] = None,
        status: str = "offline",
        max_concurrent_tasks: int = 1,
    ) -> Agent:
        """Create an agent in a workspace."""
        agent = Agent(
            workspace_id=workspace_id,
            name=name,
            owner_id=owner_id,
            runtime_mode=runtime_mode,
            runtime_config=runtime_config or {},
            instructions=instructions,
            status=status,
            max_concurrent_tasks=max_concurrent_tasks,
        )
        self._session.add(agent)
        await self._session.flush()
        return agent

    async def get(self, agent_id: str) -> Optional[Agent]:
        """Get agent by ID."""
        return await self._session.get(Agent, agent_id)

    async def list_for_workspace(
        self,
        workspace_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Agent]:
        """List agents in a workspace with optional filters."""
        stmt = select(Agent).where(Agent.workspace_id == workspace_id)
        if status:
            stmt = stmt.where(Agent.status == status)
        stmt = stmt.order_by(Agent.created_at).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        agent_id: str,
        name: Optional[str] = None,
        status: Optional[str] = None,
        instructions: Optional[str] = None,
        runtime_mode: Optional[str] = None,
        runtime_config: Optional[dict] = None,
        max_concurrent_tasks: Optional[int] = None,
    ) -> Optional[Agent]:
        """Update agent fields."""
        agent = await self.get(agent_id)
        if agent is None:
            return None
        if name is not None:
            agent.name = name
        if status is not None:
            if status not in VALID_STATUSES:
                raise ValueError(f"Invalid status: {status}")
            agent.status = status
        if instructions is not None:
            agent.instructions = instructions
        if runtime_mode is not None:
            if runtime_mode not in VALID_RUNTIME_MODES:
                raise ValueError(f"Invalid runtime_mode: {runtime_mode}")
            agent.runtime_mode = runtime_mode
        if runtime_config is not None:
            agent.runtime_config = runtime_config
        if max_concurrent_tasks is not None:
            agent.max_concurrent_tasks = max_concurrent_tasks
        await self._session.flush()
        return agent

    async def delete(self, agent_id: str) -> bool:
        """Delete an agent."""
        agent = await self.get(agent_id)
        if agent is None:
            return False
        await self._session.delete(agent)
        await self._session.flush()
        return True
