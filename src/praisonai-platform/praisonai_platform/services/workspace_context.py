"""
Workspace context service — implements WorkspaceContextProtocol for platform integration.

Provides workspace-level context and agent configuration by querying the database,
implementing the WorkspaceContextProtocol from praisonaiagents.auth.protocols.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from praisonaiagents.auth.protocols import WorkspaceContextProtocol

from ..db.models import Agent, Workspace


class PlatformWorkspaceContext(WorkspaceContextProtocol):
    """
    Platform implementation of WorkspaceContextProtocol.
    
    Provides workspace context and agent configuration by querying the platform database.
    """

    def __init__(self, workspace_id: str, session: AsyncSession):
        """
        Initialize workspace context provider.
        
        Args:
            workspace_id: ID of the workspace to provide context for
            session: Database session for queries
        """
        self.workspace_id = workspace_id
        self._session = session

    async def get_workspace_context(self, workspace_id: str) -> Optional[str]:
        """
        Get workspace-level context for agents.
        
        Returns:
            Workspace context string if found, None otherwise.
        """
        if workspace_id != self.workspace_id:
            return None

        workspace = await self._session.get(Workspace, workspace_id)
        if workspace is None:
            return None

        payload = {
            "id": workspace.id,
            "name": workspace.name,
            "slug": workspace.slug,
            "description": workspace.description,
            "settings": workspace.settings or {},
        }
        return json.dumps(payload, ensure_ascii=False, default=str)

    async def get_agent_config(
        self,
        workspace_id: str,
        agent_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get agent configuration from the platform.
        
        Args:
            agent_id: The agent identifier
            
        Returns:
            Agent configuration dict if found, None otherwise.
            Keys: id, name, runtime_mode, instructions, config, max_concurrent_tasks
        """
        if workspace_id != self.workspace_id:
            return None

        # Query for agent scoped to the workspace
        stmt = (
            select(Agent)
            .where(Agent.id == agent_id)
            .where(Agent.workspace_id == workspace_id)
        )
        result = await self._session.execute(stmt)
        agent = result.scalar_one_or_none()

        if agent is None:
            return None

        return {
            "id": agent.id,
            "name": agent.name,
            "runtime_mode": agent.runtime_mode,
            "instructions": agent.instructions,
            "config": agent.runtime_config or {},
            "max_concurrent_tasks": agent.max_concurrent_tasks,
        }
