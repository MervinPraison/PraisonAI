"""Activity log routes — GAP-9."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from praisonaiagents.auth import AuthIdentity

from ..deps import get_db, require_workspace_member
from ..schemas import ActivityLogResponse
from ...services.activity_service import ActivityService

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["activity"])


@router.get("/activity", response_model=List[ActivityLogResponse])
async def list_workspace_activity(
    workspace_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: AuthIdentity = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
):
    svc = ActivityService(session)
    logs = await svc.list_for_workspace(workspace_id, limit=limit, offset=offset)
    return [ActivityLogResponse.model_validate(log) for log in logs]


@router.get("/issues/{issue_id}/activity", response_model=List[ActivityLogResponse])
async def list_issue_activity(
    workspace_id: str,
    issue_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: AuthIdentity = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
):
    svc = ActivityService(session)
    logs = await svc.list_for_issue(issue_id, limit=limit, offset=offset)
    return [ActivityLogResponse.model_validate(log) for log in logs]
