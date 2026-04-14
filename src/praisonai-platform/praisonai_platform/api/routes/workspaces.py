"""Workspace routes."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from praisonaiagents.auth import AuthIdentity

from ..deps import get_current_user, get_db
from ..schemas import (
    MemberAdd,
    MemberResponse,
    MemberUpdate,
    WorkspaceCreate,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from ...services.member_service import MemberService
from ...services.workspace_service import WorkspaceService

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.post("/", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: WorkspaceCreate,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    ws_svc = WorkspaceService(session)
    ws = await ws_svc.create(body.name, user.id, body.slug, body.description)
    return WorkspaceResponse.model_validate(ws)


@router.get("/", response_model=List[WorkspaceResponse])
async def list_workspaces(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    ws_svc = WorkspaceService(session)
    workspaces = await ws_svc.list_for_user(user.id, limit=limit, offset=offset)
    return [WorkspaceResponse.model_validate(ws) for ws in workspaces]


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: str,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    ws_svc = WorkspaceService(session)
    ws = await ws_svc.get(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return WorkspaceResponse.model_validate(ws)


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: str,
    body: WorkspaceUpdate,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    ws_svc = WorkspaceService(session)
    ws = await ws_svc.update(workspace_id, body.name, body.description, body.settings)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return WorkspaceResponse.model_validate(ws)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: str,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    ws_svc = WorkspaceService(session)
    deleted = await ws_svc.delete(workspace_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workspace not found")


# ── Members ──────────────────────────────────────────────────────────────────


@router.post("/{workspace_id}/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def add_member(
    workspace_id: str,
    body: MemberAdd,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    member_svc = MemberService(session)
    member = await member_svc.add(workspace_id, body.user_id, body.role)
    return MemberResponse.model_validate(member)


@router.get("/{workspace_id}/members", response_model=List[MemberResponse])
async def list_members(
    workspace_id: str,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    member_svc = MemberService(session)
    members = await member_svc.list_members(workspace_id)
    return [MemberResponse.model_validate(m) for m in members]


@router.patch("/{workspace_id}/members/{user_id}", response_model=MemberResponse)
async def update_member_role(
    workspace_id: str,
    user_id: str,
    body: MemberUpdate,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    member_svc = MemberService(session)
    member = await member_svc.update_role(workspace_id, user_id, body.role)
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    return MemberResponse.model_validate(member)


@router.delete("/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    workspace_id: str,
    user_id: str,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    member_svc = MemberService(session)
    removed = await member_svc.remove(workspace_id, user_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Member not found")
