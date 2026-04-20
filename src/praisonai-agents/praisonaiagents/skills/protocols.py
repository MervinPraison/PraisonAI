"""Protocols for pluggable skill sources and invocation policies.

Core SDK stays protocol-driven (see AGENTS.md §4.1). These protocols let
wrappers or paid tiers plug in alternative skill storage (HTTP registry,
plugin bundle, enterprise policy) without touching the core.
"""

from __future__ import annotations

from typing import Protocol, Iterable, Optional, runtime_checkable

from .models import SkillProperties


@runtime_checkable
class SkillSourceProtocol(Protocol):
    """Abstract source of skills.

    Implementations may back skills onto the filesystem (default), an
    HTTP registry, a plugin directory, or an enterprise policy server.
    """

    def discover(self) -> Iterable[SkillProperties]:
        """Return every skill this source can supply."""
        ...

    def load_instructions(self, name: str) -> Optional[str]:
        """Return the SKILL.md body for ``name``, or None if unknown."""
        ...


@runtime_checkable
class SkillInvocationPolicyProtocol(Protocol):
    """Gatekeeps whether user/model can invoke a given skill."""

    def can_model_invoke(self, props: SkillProperties) -> bool:
        ...

    def can_user_invoke(self, props: SkillProperties) -> bool:
        ...


@runtime_checkable
class SkillMutatorProtocol(Protocol):
    """Agent-managed skill CRUD operations.
    
    Allows agents to create, edit, and manage their own skills at runtime.
    Implementations should provide safe-by-default behavior (e.g., propose mode).
    """

    def create(self, name: str, content: str, category: Optional[str] = None,
               propose: bool = True) -> str:
        """Create a new skill.
        
        Args:
            name: Skill name (must be valid identifier)
            content: Full SKILL.md content
            category: Optional category for organization
            propose: If True, stage for approval; if False, create directly
            
        Returns:
            Status message describing the action taken
        """
        ...

    def patch(self, name: str, old_string: str, new_string: str,
              file_path: Optional[str] = None, replace_all: bool = False,
              propose: bool = True) -> str:
        """Patch an existing skill using find-replace.
        
        Args:
            name: Skill name to modify
            old_string: Text to find and replace
            new_string: Replacement text
            file_path: Optional specific file within skill (defaults to SKILL.md)
            replace_all: Replace all occurrences vs first only
            propose: If True, stage for approval; if False, apply directly
            
        Returns:
            Status message describing the action taken
        """
        ...

    def edit(self, name: str, content: str, propose: bool = True) -> str:
        """Replace entire skill content.
        
        Args:
            name: Skill name to edit
            content: New complete content
            propose: If True, stage for approval; if False, apply directly
            
        Returns:
            Status message describing the action taken
        """
        ...

    def delete(self, name: str, propose: bool = True) -> str:
        """Delete a skill entirely.
        
        Args:
            name: Skill name to delete
            propose: If True, stage for approval; if False, delete directly
            
        Returns:
            Status message describing the action taken
        """
        ...

    def write_file(self, name: str, file_path: str, file_content: str,
                   propose: bool = True) -> str:
        """Write a file within a skill directory.
        
        Args:
            name: Skill name
            file_path: Relative path within skill directory
            file_content: File contents to write
            propose: If True, stage for approval; if False, write directly
            
        Returns:
            Status message describing the action taken
        """
        ...

    def remove_file(self, name: str, file_path: str, propose: bool = True) -> str:
        """Remove a file from a skill directory.
        
        Args:
            name: Skill name
            file_path: Relative path within skill directory
            propose: If True, stage for approval; if False, remove directly
            
        Returns:
            Status message describing the action taken
        """
        ...

    def list_pending(self) -> list[dict]:
        """List all pending skill mutations awaiting approval.
        
        Returns:
            List of dictionaries with keys: name, action, status, created_at
        """
        ...

    def approve(self, name: str) -> str:
        """Approve a pending skill mutation.
        
        Args:
            name: Skill name to approve
            
        Returns:
            Status message describing the action taken
        """
        ...

    def reject(self, name: str) -> str:
        """Reject a pending skill mutation.
        
        Args:
            name: Skill name to reject
            
        Returns:
            Status message describing the action taken
        """
        ...
