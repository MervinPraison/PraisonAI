"""Issue dependency routes."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from praisonaiagents.auth import AuthIdentity

from ..deps import get_db, require_workspace_member
from ..schemas import DependencyCreate, DependencyResponse
from ...services.dependency_service import DependencyService

router = APIRouter(
    prefix="/workspaces/{workspace_id}/issues/{issue_id}/dependencies",
    tags=["dependencies"],
)


@router.post("/", response_model=DependencyResponse, status_code=status.HTTP_201_CREATED)
async def create_dependency(
    workspace_id: str,
    issue_id: str,
    body: DependencyCreate,
    user: AuthIdentity = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
):
    svc = DependencyService(session)
    dep = await svc.create(issue_id, body.depends_on_issue_id, body.type)
    return DependencyResponse.model_validate(dep)


@router.get("/", response_model=List[DependencyResponse])
async def list_dependencies(
    workspace_id: str,
    issue_id: str,
    user: AuthIdentity = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
):
    svc = DependencyService(session)
    deps = await svc.list_for_issue(issue_id)
    return [DependencyResponse.model_validate(d) for d in deps]


@router.delete("/{dep_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dependency(
    workspace_id: str,
    issue_id: str,
    dep_id: str,
    user: AuthIdentity = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
):
    svc = DependencyService(session)
    deleted = await svc.delete(dep_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Dependency not found")
