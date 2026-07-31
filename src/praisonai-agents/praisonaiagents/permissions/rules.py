"""
Permission rules for PraisonAI Agents.

Provides pattern-based permission rules with allow/deny/ask actions.
"""

import fnmatch
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class PermissionAction(str, Enum):
    """Actions for permission rules."""
    
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class PermissionMode(str, Enum):
    """
    Permission modes for agent execution (Claude Code parity).
    
    These modes control how permissions are handled during agent execution:
    - DEFAULT: Standard permission checking with allow/deny/ask rules
    - ACCEPT_EDITS: Auto-accept file edit operations
    - DONT_ASK: Auto-deny any prompts that would require user input
    - BYPASS: Skip all permission checks (dangerous, use with caution)
    - PLAN: Read-only exploration mode, no write operations allowed
    """
    
    DEFAULT = "default"
    ACCEPT_EDITS = "accept_edits"
    DONT_ASK = "dont_ask"
    BYPASS = "bypass_permissions"
    PLAN = "plan"

    @classmethod
    def resolve(cls, value: Any) -> Optional["PermissionMode"]:
        """Resolve a preset name/alias to a canonical ``PermissionMode``.

        This is the single place that maps the many historical spellings for
        "how much the agent may do" onto one enum, so CLI, YAML and Python all
        agree. Returns ``None`` for values that are not a permission preset
        (e.g. the deny-set presets ``safe``/``read_only``/``full``/``off``),
        letting callers fall through to their existing handling.

        Recognised aliases (case-insensitive, ``-``/``_`` interchangeable):
        - ``plan`` … PLAN (read-only)
        - ``bypass``, ``bypass_permissions``, ``yolo``, ``full_auto`` … BYPASS
        - ``accept_edits``, ``auto_edit`` … ACCEPT_EDITS
        - ``dont_ask``, ``reject``, ``no_ask`` … DONT_ASK
        - ``default``, ``ask``, ``suggest``, ``prompt`` … DEFAULT

        Note: the deny-set presets ``safe``/``read_only``/``full``/``off`` are
        deliberately *not* modes and return ``None`` here — they are handled by
        their own deny-set machinery in ``Agent``.
        """
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            return None
        key = value.strip().lower().replace("-", "_")
        return _MODE_ALIASES.get(key)


# Deprecated/alternate spellings (AutonomyMode / ApprovalMode / CLI flags) that
# resolve onto the single ``PermissionMode``. Kept as thin aliases so the same
# preset name means the same thing across every surface (backward-compatible).
_MODE_ALIASES: Dict[str, PermissionMode] = {
    "default": PermissionMode.DEFAULT,
    "ask": PermissionMode.DEFAULT,
    "suggest": PermissionMode.DEFAULT,
    "prompt": PermissionMode.DEFAULT,
    "plan": PermissionMode.PLAN,
    "accept_edits": PermissionMode.ACCEPT_EDITS,
    "auto_edit": PermissionMode.ACCEPT_EDITS,
    "dont_ask": PermissionMode.DONT_ASK,
    "no_ask": PermissionMode.DONT_ASK,
    "reject": PermissionMode.DONT_ASK,
    "bypass": PermissionMode.BYPASS,
    "bypass_permissions": PermissionMode.BYPASS,
    "yolo": PermissionMode.BYPASS,
    "full_auto": PermissionMode.BYPASS,
}


@dataclass
class PermissionRule:
    """
    A pattern-based permission rule.
    
    Attributes:
        pattern: Glob or regex pattern to match against
        action: What to do when pattern matches (allow/deny/ask)
        description: Human-readable description
        is_regex: Whether pattern is a regex (default: glob)
        priority: Higher priority rules are checked first
        agent_name: Optional agent name this rule applies to
        enabled: Whether the rule is active
    """
    
    pattern: str
    action: PermissionAction = PermissionAction.ASK
    description: str = ""
    is_regex: bool = False
    priority: int = 0
    agent_name: Optional[str] = None
    enabled: bool = True
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)
    
    def matches(self, target: str) -> bool:
        """
        Check if this rule matches the target.
        
        Args:
            target: The string to match against (e.g., "bash:rm -rf /tmp")
            
        Returns:
            True if the pattern matches
        """
        if not self.enabled:
            return False
        
        if self.is_regex:
            try:
                return bool(re.match(self.pattern, target))
            except re.error:
                return False
        else:
            return fnmatch.fnmatch(target, self.pattern)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert rule to dictionary."""
        return {
            "id": self.id,
            "pattern": self.pattern,
            "action": self.action.value,
            "description": self.description,
            "is_regex": self.is_regex,
            "priority": self.priority,
            "agent_name": self.agent_name,
            "enabled": self.enabled,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PermissionRule":
        """Create rule from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            pattern=data.get("pattern", "*"),
            action=PermissionAction(data.get("action", "ask")),
            description=data.get("description", ""),
            is_regex=data.get("is_regex", False),
            priority=data.get("priority", 0),
            agent_name=data.get("agent_name"),
            enabled=data.get("enabled", True),
            created_at=data.get("created_at", time.time()),
        )
    
    @classmethod
    def from_config(cls, pattern: str, action: str, **kwargs) -> "PermissionRule":
        """
        Create rule from configuration (YAML/CLI/Python).
        
        Args:
            pattern: The permission pattern (e.g., "read:*", "bash:git *")
            action: The action string (allow/deny/ask)
            **kwargs: Optional attributes like description, priority, is_regex
            
        Returns:
            PermissionRule instance
        """
        return cls(
            pattern=pattern,
            action=PermissionAction(action),
            description=kwargs.get("description", f"Rule for {pattern}"),
            is_regex=kwargs.get("is_regex", False),
            priority=kwargs.get("priority", 0),
            agent_name=kwargs.get("agent_name"),
            enabled=kwargs.get("enabled", True),
        )


@dataclass
class PermissionResult:
    """
    Result of a permission check.
    
    Attributes:
        action: The resulting action (allow/deny/ask)
        rule: The rule that matched (if any)
        target: The target that was checked
        reason: Human-readable reason
        approved: Whether the action was approved (for ask actions)
    """
    
    action: PermissionAction
    rule: Optional[PermissionRule] = None
    target: str = ""
    reason: str = ""
    approved: Optional[bool] = None
    
    @property
    def is_allowed(self) -> bool:
        """Check if the action is allowed."""
        if self.action == PermissionAction.ALLOW:
            return True
        if self.action == PermissionAction.ASK:
            return self.approved is True
        return False
    
    @property
    def is_denied(self) -> bool:
        """Check if the action is denied."""
        if self.action == PermissionAction.DENY:
            return True
        if self.action == PermissionAction.ASK:
            return self.approved is False
        return False
    
    @property
    def needs_approval(self) -> bool:
        """Check if the action needs user approval."""
        return self.action == PermissionAction.ASK and self.approved is None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "action": self.action.value,
            "rule_id": self.rule.id if self.rule else None,
            "target": self.target,
            "reason": self.reason,
            "approved": self.approved,
            "is_allowed": self.is_allowed,
            "is_denied": self.is_denied,
            "needs_approval": self.needs_approval,
        }


@dataclass
class PersistentApproval:
    """
    A persistent approval for a pattern.
    
    Used to remember user decisions for future requests.
    """
    
    pattern: str
    approved: bool
    scope: str = "once"  # once, session, always
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    agent_name: Optional[str] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # True only when ``pattern`` was auto-generated by the reusable
    # command-prefix scope derivation (arity.derive_pattern). Gates the
    # bare-prefix fallback in ``matches`` so user-authored globs like
    # ``bash:rm *`` keep exact fnmatch semantics.
    derived: bool = False
    
    def is_valid(self) -> bool:
        """Check if the approval is still valid."""
        if self.expires_at and time.time() > self.expires_at:
            return False
        return True
    
    def matches(self, target: str, agent_name: Optional[str] = None) -> bool:
        """Check if this approval applies to the target."""
        if not self.is_valid():
            return False
        
        # An approval scoped to a specific agent must never match a call that
        # can't prove it's that agent — including calls with no agent_name at
        # all. ``agent_name != self.agent_name`` covers both "different name"
        # and "no name" (None != "trusted-agent" is True), closing the bypass
        # while leaving unscoped approvals (self.agent_name is None) unaffected.
        if self.agent_name is not None and agent_name != self.agent_name:
            return False
        
        if fnmatch.fnmatch(target, self.pattern):
            return True

        # A reusable command-prefix scope like "bash:git status *" is meant to
        # cover the bare command too (e.g. "bash:git status" with no trailing
        # args), which a plain "<prefix> *" glob would miss. Match the prefix
        # exactly as well, without altering the general matching hot path.
        #
        # Gated on ``self.derived`` so this ONLY applies to patterns produced by
        # the reusable-scope derivation (arity.derive_pattern). User-authored
        # globs — shell or otherwise, e.g. "bash:rm *" or "read:/secret *" —
        # keep their exact fnmatch semantics and this never changes their
        # allow/deny decisions.
        if self.derived and self.pattern.endswith(" *") and self.pattern.startswith(
            ("bash:", "shell:")
        ):
            bare = self.pattern[:-2]
            if target == bare:
                return True

        return False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert approval to dictionary."""
        return {
            "id": self.id,
            "pattern": self.pattern,
            "approved": self.approved,
            "scope": self.scope,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "agent_name": self.agent_name,
            "derived": self.derived,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PersistentApproval":
        """Create approval from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            pattern=data.get("pattern", "*"),
            approved=data.get("approved", False),
            scope=data.get("scope", "once"),
            created_at=data.get("created_at", time.time()),
            expires_at=data.get("expires_at"),
            agent_name=data.get("agent_name"),
            derived=data.get("derived", False),
        )
