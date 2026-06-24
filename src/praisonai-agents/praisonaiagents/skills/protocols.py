"""Protocols for pluggable skill sources and invocation policies.

Core SDK stays protocol-driven (see AGENTS.md §4.1). These protocols let
wrappers or paid tiers plug in alternative skill storage (HTTP registry,
plugin bundle, enterprise policy) without touching the core.
"""

from __future__ import annotations

from typing import Protocol, Iterable, Optional, runtime_checkable, List, Dict, Any

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
    Implementations should provide safe-by-default behaviour: use ``propose=True``
    (default) to stage mutations for human approval before writing to disk.
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


@runtime_checkable
class SkillsCatalogProtocol(Protocol):
    """Metadata listing for skills — UI catalog pages."""

    def list_skills(self) -> List[Dict[str, Any]]:
        """Return skill metadata dicts (name, description, location)."""
        ...


@runtime_checkable
class SkillReviewProtocol(Protocol):
    """Policy for the autonomous skill self-improvement loop.

    After a task finishes, an opt-in guarded review pass asks the agent
    whether the session revealed a reusable technique worth capturing as a
    skill. ``should_review`` decides *whether* to run the pass and
    ``review_prompt`` produces the directive given to the agent. Both take a
    lightweight trajectory dict so wrappers/plugins can swap the policy
    without depending on core internals.
    """

    def should_review(self, trajectory: Dict[str, Any]) -> bool:
        """Return True if the finished session warrants a skill review."""
        ...

    def review_prompt(self, trajectory: Dict[str, Any]) -> str:
        """Return the directive prompt for the guarded review turn."""
        ...


class DefaultSkillReviewPolicy:
    """Default, conservative skill-review policy.

    Triggers only when the session did real work (at least ``min_tool_calls``
    tool invocations, default 1) and asks the agent to create or patch a
    single skill if — and only if — a durable, reusable technique emerged.
    """

    #: Hard cap on how much of the original prompt is echoed into the review
    #: directive. Bounds token cost and shrinks the prompt-injection surface.
    MAX_PROMPT_CHARS = 500

    def __init__(self, min_tool_calls: int = 1):
        # Clamp to >= 1: a value of 0 would trigger a review LLM call after
        # every single chat() (even no-op turns that used no tools), silently
        # doubling API cost. The minimum unit of "real work" is one tool call.
        self.min_tool_calls = max(1, int(min_tool_calls))

    def should_review(self, trajectory: Dict[str, Any]) -> bool:
        tools_used = trajectory.get("tools_used") or []
        return len(tools_used) >= self.min_tool_calls

    def review_prompt(self, trajectory: Dict[str, Any]) -> str:
        prompt = str(trajectory.get("prompt", "")).strip()
        if len(prompt) > self.MAX_PROMPT_CHARS:
            prompt = prompt[: self.MAX_PROMPT_CHARS] + "…"
        tools_used = trajectory.get("tools_used") or []
        tools_str = ", ".join(str(t) for t in tools_used) if tools_used else "none"
        return (
            "You have just finished a task. Reflect ONLY on whether this "
            "session revealed a durable, reusable technique, or exposed a "
            "loaded skill that was wrong or incomplete.\n\n"
            f"Original task: {prompt}\n"
            f"Tools used: {tools_str}\n\n"
            "If — and only if — there is a genuinely reusable capability worth "
            "saving, call the `skill_manage` tool to create a new skill or "
            "patch an existing one. Use a clear, hyphenated skill name and a "
            "concise SKILL.md body capturing the reusable steps. "
            "If nothing durable was learned, reply with exactly 'NO_SKILL' "
            "and do not call any tool."
        )


def list_skills_for_api() -> List[Dict[str, Any]]:
    """Default catalog adapter using SkillManager when available."""
    try:
        from .manager import SkillManager

        manager = SkillManager()
        return [
            {
                "name": s.name,
                "description": s.description,
                "location": getattr(s, "location", ""),
            }
            for s in manager.get_available_skills()
        ]
    except Exception:
        return []
