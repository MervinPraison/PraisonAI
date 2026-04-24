"""Database models for praisonai-platform."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


def _uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)


class User(Base):
    """User model for authentication."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    memberships: Mapped[List["Member"]] = relationship("Member", back_populates="user")


class Workspace(Base):
    """Workspace model for organizing work."""
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    settings: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True, default=dict)
    issue_prefix: Mapped[str] = mapped_column(String, default="ISSUE")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    members: Mapped[List["Member"]] = relationship("Member", back_populates="workspace")
    projects: Mapped[List["Project"]] = relationship("Project", back_populates="workspace")
    issues: Mapped[List["Issue"]] = relationship("Issue", back_populates="workspace")
    agents: Mapped[List["Agent"]] = relationship("Agent", back_populates="workspace")


class Member(Base):
    """Workspace membership model."""
    __tablename__ = "members"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String, ForeignKey("workspaces.id"), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="member")  # owner, admin, member
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="memberships")
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="members")

    __table_args__ = (
        UniqueConstraint("user_id", "workspace_id", name="uq_member_user_workspace"),
    )


class Project(Base):
    """Project model for organizing issues."""
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String, ForeignKey("workspaces.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    settings: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="projects")
    issues: Mapped[List["Issue"]] = relationship("Issue", back_populates="project")


class Issue(Base):
    """Issue model for tracking work items."""
    __tablename__ = "issues"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String, ForeignKey("workspaces.id"), nullable=False)
    project_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("projects.id"), nullable=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="backlog")
    priority: Mapped[str] = mapped_column(String, nullable=False, default="medium")
    assignee_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_by_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    issue_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="issues")
    project: Mapped[Optional["Project"]] = relationship("Project", back_populates="issues")
    comments: Mapped[List["Comment"]] = relationship("Comment", back_populates="issue")
    labels: Mapped[List["IssueLabelLink"]] = relationship("IssueLabelLink", back_populates="issue")


class Comment(Base):
    """Comment model for issue discussions."""
    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    issue_id: Mapped[str] = mapped_column(String, ForeignKey("issues.id"), nullable=False)
    author_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    issue: Mapped["Issue"] = relationship("Issue", back_populates="comments")


class Agent(Base):
    """Agent model for AI agents in workspace."""
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String, ForeignKey("workspaces.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="idle")
    config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="agents")


class IssueLabel(Base):
    """Label definitions for issues."""
    __tablename__ = "issue_labels"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String, ForeignKey("workspaces.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    color: Mapped[str] = mapped_column(String, nullable=False, default="#000000")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    issues: Mapped[List["IssueLabelLink"]] = relationship("IssueLabelLink", back_populates="label")


class IssueLabelLink(Base):
    """Many-to-many relationship between issues and labels."""
    __tablename__ = "issue_label_links"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    issue_id: Mapped[str] = mapped_column(String, ForeignKey("issues.id"), nullable=False)
    label_id: Mapped[str] = mapped_column(String, ForeignKey("issue_labels.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    # Relationships
    issue: Mapped["Issue"] = relationship("Issue", back_populates="labels")
    label: Mapped["IssueLabel"] = relationship("IssueLabel", back_populates="issues")

    __table_args__ = (
        UniqueConstraint("issue_id", "label_id", name="uq_issue_label"),
    )


class IssueDependency(Base):
    """Issue dependency relationships."""
    __tablename__ = "issue_dependencies"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    issue_id: Mapped[str] = mapped_column(String, ForeignKey("issues.id"), nullable=False)
    depends_on_id: Mapped[str] = mapped_column(String, ForeignKey("issues.id"), nullable=False)
    dependency_type: Mapped[str] = mapped_column(String, nullable=False)  # blocks, blocked_by, related
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    __table_args__ = (
        UniqueConstraint("issue_id", "depends_on_id", "dependency_type", name="uq_issue_dependency"),
    )


class ActivityLog(Base):
    """Activity log for tracking changes."""
    __tablename__ = "activity_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(String, ForeignKey("workspaces.id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)  # issue, project, workspace, etc.
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)  # created, updated, deleted, etc.
    actor_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)