"""Pydantic schemas for API request/response."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr


# ── Auth ─────────────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    token: str
    user: UserResponse


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    avatar_url: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# Fix forward reference
TokenResponse.model_rebuild()


# ── Workspace ────────────────────────────────────────────────────────────────


class WorkspaceCreate(BaseModel):
    name: str
    slug: Optional[str] = None
    description: Optional[str] = None


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: Optional[str] = None
    settings: Dict[str, Any] = {}
    created_at: datetime

    class Config:
        from_attributes = True


# ── Member ───────────────────────────────────────────────────────────────────


class MemberAdd(BaseModel):
    user_id: str
    role: str = "member"


class MemberUpdate(BaseModel):
    role: str


class MemberResponse(BaseModel):
    id: str
    workspace_id: str
    user_id: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


# ── Project ──────────────────────────────────────────────────────────────────


class ProjectCreate(BaseModel):
    title: str
    description: Optional[str] = None
    icon: Optional[str] = None
    lead_type: Optional[str] = None
    lead_id: Optional[str] = None


class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    lead_type: Optional[str] = None
    lead_id: Optional[str] = None


class ProjectResponse(BaseModel):
    id: str
    workspace_id: str
    title: str
    description: Optional[str] = None
    icon: Optional[str] = None
    status: str
    lead_type: Optional[str] = None
    lead_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── Issue ────────────────────────────────────────────────────────────────────


class IssueCreate(BaseModel):
    title: str
    description: Optional[str] = None
    project_id: Optional[str] = None
    status: str = "backlog"
    priority: str = "none"
    assignee_type: Optional[str] = None
    assignee_id: Optional[str] = None
    parent_issue_id: Optional[str] = None
    acceptance_criteria: Optional[List[str]] = None


class IssueUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee_type: Optional[str] = None
    assignee_id: Optional[str] = None
    project_id: Optional[str] = None


class IssueResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    status: str
    priority: str
    assignee_type: Optional[str] = None
    assignee_id: Optional[str] = None
    creator_type: Optional[str] = None
    creator_id: Optional[str] = None
    number: Optional[int] = None
    identifier: Optional[str] = None
    parent_issue_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── Comment ──────────────────────────────────────────────────────────────────


class CommentCreate(BaseModel):
    content: str
    parent_id: Optional[str] = None


class CommentResponse(BaseModel):
    id: str
    issue_id: str
    author_type: Optional[str] = None
    author_id: Optional[str] = None
    parent_id: Optional[str] = None
    content: str
    type: str
    created_at: datetime

    class Config:
        from_attributes = True


# ── Agent ────────────────────────────────────────────────────────────────


class AgentCreate(BaseModel):
    name: str
    runtime_mode: str = "local"
    runtime_config: Optional[Dict[str, Any]] = None
    instructions: Optional[str] = None
    max_concurrent_tasks: int = 1


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    instructions: Optional[str] = None
    runtime_mode: Optional[str] = None
    runtime_config: Optional[Dict[str, Any]] = None
    max_concurrent_tasks: Optional[int] = None


class AgentResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    avatar_url: Optional[str] = None
    runtime_mode: str
    instructions: Optional[str] = None
    status: str
    max_concurrent_tasks: int
    owner_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── Label ────────────────────────────────────────────────────────────────


class LabelCreate(BaseModel):
    name: str
    color: str = "#6B7280"


class LabelUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None


class LabelResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    color: str

    class Config:
        from_attributes = True


# ── IssueDependency ──────────────────────────────────────────────────────


class DependencyCreate(BaseModel):
    depends_on_issue_id: str
    type: str = "blocks"


class DependencyResponse(BaseModel):
    id: str
    issue_id: str
    depends_on_issue_id: str
    type: str

    class Config:
        from_attributes = True


# ── ActivityLog ──────────────────────────────────────────────────────────


class ActivityLogResponse(BaseModel):
    id: str
    workspace_id: str
    entity_type: str
    entity_id: str
    issue_id: Optional[str] = None
    actor_type: Optional[str] = None
    actor_id: Optional[str] = None
    action: str
    details: Dict[str, Any] = {}
    created_at: datetime

    class Config:
        from_attributes = True
