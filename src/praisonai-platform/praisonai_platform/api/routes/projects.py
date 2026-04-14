"""Project routes."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from praisonaiagents.auth import AuthIdentity

from ..deps import get_current_user, get_db, require_workspace_member
from ..schemas import ProjectCreate, ProjectResponse, ProjectUpdate
from ...services.project_service import ProjectService

router = APIRouter(prefix="/workspaces/{workspace_id}/projects", tags=["projects"])


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    workspace_id: str,
    body: ProjectCreate,
    user: AuthIdentity = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
):
    svc = ProjectService(session)
    project = await svc.create(
        workspace_id=workspace_id,
        title=body.title,
        description=body.description,
        icon=body.icon,
        lead_type=body.lead_type,
        lead_id=body.lead_id,
    )
    return ProjectResponse.model_validate(project)


@router.get("/", response_model=List[ProjectResponse])
async def list_projects(
    workspace_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: AuthIdentity = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
):
    svc = ProjectService(session)
    projects = await svc.list_for_workspace(workspace_id, limit=limit, offset=offset)
    return [ProjectResponse.model_validate(p) for p in projects]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    workspace_id: str,
    project_id: str,
    user: AuthIdentity = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
):
    svc = ProjectService(session)
    project = await svc.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectResponse.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    workspace_id: str,
    project_id: str,
    body: ProjectUpdate,
    user: AuthIdentity = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
):
    svc = ProjectService(session)
    project = await svc.update(
        project_id,
        title=body.title,
        description=body.description,
        status=body.status,
        lead_type=body.lead_type,
        lead_id=body.lead_id,
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    workspace_id: str,
    project_id: str,
    user: AuthIdentity = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
):
    svc = ProjectService(session)
    deleted = await svc.delete(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/{project_id}/stats")
async def project_stats(
    workspace_id: str,
    project_id: str,
    user: AuthIdentity = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
):
    svc = ProjectService(session)
    return await svc.get_stats(project_id)
