"""Agent routes."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from praisonaiagents.auth import AuthIdentity

from ..deps import get_current_user, get_db
from ..schemas import AgentCreate, AgentResponse, AgentUpdate
from ...services.agent_service import AgentService

router = APIRouter(prefix="/workspaces/{workspace_id}/agents", tags=["agents"])


@router.post("/", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    workspace_id: str,
    body: AgentCreate,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    svc = AgentService(session)
    agent = await svc.create(
        workspace_id=workspace_id,
        name=body.name,
        owner_id=user.id,
        runtime_mode=body.runtime_mode,
        runtime_config=body.runtime_config,
        instructions=body.instructions,
        max_concurrent_tasks=body.max_concurrent_tasks,
    )
    return AgentResponse.model_validate(agent)


@router.get("/", response_model=List[AgentResponse])
async def list_agents(
    workspace_id: str,
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    svc = AgentService(session)
    agents = await svc.list_for_workspace(workspace_id, status=status_filter, limit=limit, offset=offset)
    return [AgentResponse.model_validate(a) for a in agents]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    workspace_id: str,
    agent_id: str,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    svc = AgentService(session)
    agent = await svc.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentResponse.model_validate(agent)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    workspace_id: str,
    agent_id: str,
    body: AgentUpdate,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    svc = AgentService(session)
    agent = await svc.update(
        agent_id,
        name=body.name,
        status=body.status,
        instructions=body.instructions,
        runtime_mode=body.runtime_mode,
        runtime_config=body.runtime_config,
        max_concurrent_tasks=body.max_concurrent_tasks,
    )
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentResponse.model_validate(agent)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    workspace_id: str,
    agent_id: str,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    svc = AgentService(session)
    deleted = await svc.delete(agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Agent not found")
