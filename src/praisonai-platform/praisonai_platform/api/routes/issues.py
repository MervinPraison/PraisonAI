"""Issue and Comment routes."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from praisonaiagents.auth import AuthIdentity

from ..deps import get_current_user, get_db
from ..schemas import (
    CommentCreate,
    CommentResponse,
    IssueCreate,
    IssueResponse,
    IssueUpdate,
)
from ...services.activity_service import ActivityService
from ...services.comment_service import CommentService
from ...services.issue_service import IssueService

router = APIRouter(prefix="/workspaces/{workspace_id}/issues", tags=["issues"])


@router.post("/", response_model=IssueResponse, status_code=status.HTTP_201_CREATED)
async def create_issue(
    workspace_id: str,
    body: IssueCreate,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    svc = IssueService(session)
    issue = await svc.create(
        workspace_id=workspace_id,
        title=body.title,
        creator_id=user.id,
        creator_type="user" if user.is_user else "agent",
        project_id=body.project_id,
        description=body.description,
        status=body.status,
        priority=body.priority,
        assignee_type=body.assignee_type,
        assignee_id=body.assignee_id,
        parent_issue_id=body.parent_issue_id,
        acceptance_criteria=body.acceptance_criteria,
    )
    act_svc = ActivityService(session)
    await act_svc.log(
        workspace_id, "issue.created",
        actor_type="user" if user.is_user else "agent",
        actor_id=user.id, issue_id=issue.id,
        details={"title": issue.title, "identifier": issue.identifier},
    )
    return IssueResponse.model_validate(issue)


@router.get("/", response_model=List[IssueResponse])
async def list_issues(
    workspace_id: str,
    status_filter: Optional[str] = Query(None, alias="status"),
    project_id: Optional[str] = None,
    assignee_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    svc = IssueService(session)
    issues = await svc.list_for_workspace(
        workspace_id,
        status=status_filter,
        project_id=project_id,
        assignee_id=assignee_id,
        limit=limit,
        offset=offset,
    )
    return [IssueResponse.model_validate(i) for i in issues]


@router.get("/{issue_id}", response_model=IssueResponse)
async def get_issue(
    workspace_id: str,
    issue_id: str,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    svc = IssueService(session)
    issue = await svc.get(issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    return IssueResponse.model_validate(issue)


@router.patch("/{issue_id}", response_model=IssueResponse)
async def update_issue(
    workspace_id: str,
    issue_id: str,
    body: IssueUpdate,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    svc = IssueService(session)
    issue = await svc.update(
        issue_id,
        title=body.title,
        description=body.description,
        status=body.status,
        priority=body.priority,
        assignee_type=body.assignee_type,
        assignee_id=body.assignee_id,
        project_id=body.project_id,
    )
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    act_svc = ActivityService(session)
    await act_svc.log(
        workspace_id, "issue.updated",
        actor_type="user" if user.is_user else "agent",
        actor_id=user.id, issue_id=issue.id,
        details={"fields": body.model_dump(exclude_none=True)},
    )
    return IssueResponse.model_validate(issue)


@router.delete("/{issue_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_issue(
    workspace_id: str,
    issue_id: str,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    svc = IssueService(session)
    deleted = await svc.delete(issue_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Issue not found")


# ── Comments ─────────────────────────────────────────────────────────────────


@router.post("/{issue_id}/comments", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def add_comment(
    workspace_id: str,
    issue_id: str,
    body: CommentCreate,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    svc = CommentService(session)
    comment = await svc.create(
        issue_id=issue_id,
        author_id=user.id,
        content=body.content,
        author_type="member" if user.is_user else "agent",
        parent_id=body.parent_id,
    )
    return CommentResponse.model_validate(comment)


@router.get("/{issue_id}/comments", response_model=List[CommentResponse])
async def list_comments(
    workspace_id: str,
    issue_id: str,
    user: AuthIdentity = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    svc = CommentService(session)
    comments = await svc.list_for_issue(issue_id)
    return [CommentResponse.model_validate(c) for c in comments]
