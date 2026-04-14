"""Label routes — workspace labels and issue-label linking."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from praisonaiagents.auth import AuthIdentity

from ..deps import get_current_user, get_db
from ..schemas import LabelCreate, LabelResponse, LabelUpdate
from ...services.label_service import LabelService

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["labels"])


@router.post("/labels", response_model=LabelResponse, status_code=status.HTTP_201_CREATED)
async def create_label(
    workspace_id: str,
    body: LabelCreate,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    svc = LabelService(session)
    label = await svc.create(workspace_id, body.name, body.color)
    return LabelResponse.model_validate(label)


@router.get("/labels", response_model=List[LabelResponse])
async def list_labels(
    workspace_id: str,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    svc = LabelService(session)
    labels = await svc.list_for_workspace(workspace_id)
    return [LabelResponse.model_validate(l) for l in labels]


@router.patch("/labels/{label_id}", response_model=LabelResponse)
async def update_label(
    workspace_id: str,
    label_id: str,
    body: LabelUpdate,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    svc = LabelService(session)
    label = await svc.update(label_id, body.name, body.color)
    if label is None:
        raise HTTPException(status_code=404, detail="Label not found")
    return LabelResponse.model_validate(label)


@router.delete("/labels/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_label(
    workspace_id: str,
    label_id: str,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    svc = LabelService(session)
    deleted = await svc.delete(label_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Label not found")


# ── Issue-Label linking ────────────────────────────────────────────────


@router.post("/issues/{issue_id}/labels/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
async def add_label_to_issue(
    workspace_id: str,
    issue_id: str,
    label_id: str,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    svc = LabelService(session)
    await svc.add_to_issue(issue_id, label_id)


@router.delete("/issues/{issue_id}/labels/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_label_from_issue(
    workspace_id: str,
    issue_id: str,
    label_id: str,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    svc = LabelService(session)
    await svc.remove_from_issue(issue_id, label_id)


@router.get("/issues/{issue_id}/labels", response_model=List[LabelResponse])
async def list_issue_labels(
    workspace_id: str,
    issue_id: str,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    svc = LabelService(session)
    labels = await svc.list_for_issue(issue_id)
    return [LabelResponse.model_validate(l) for l in labels]
