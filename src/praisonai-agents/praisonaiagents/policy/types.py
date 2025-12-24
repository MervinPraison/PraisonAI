"""
Policy Types for PraisonAI Agents.

Defines the core types for the policy engine.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


class PolicyAction(str, Enum):
    """Action to take when a policy matches."""
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"  # Require user confirmation
    LOG = "log"  # Allow but log the action
    RATE_LIMIT = "rate_limit"


@dataclass
class PolicyResult:
    """Result of a policy check."""
    allowed: bool
    action: PolicyAction
    policy_name: Optional[str] = None
    rule_name: Optional[str] = None
    reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def allow(cls, reason: Optional[str] = None) -> "PolicyResult":
        """Create an allow result."""
        return cls(allowed=True, action=PolicyAction.ALLOW, reason=reason)
    
    @classmethod
    def deny(cls, reason: str, policy_name: Optional[str] = None) -> "PolicyResult":
        """Create a deny result."""
        return cls(
            allowed=False,
            action=PolicyAction.DENY,
            policy_name=policy_name,
            reason=reason
        )
    
    @classmethod
    def ask(cls, reason: str) -> "PolicyResult":
        """Create an ask result (requires confirmation)."""
        return cls(allowed=False, action=PolicyAction.ASK, reason=reason)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "allowed": self.allowed,
            "action": self.action.value,
            "policy_name": self.policy_name,
            "rule_name": self.rule_name,
            "reason": self.reason,
            "metadata": self.metadata
        }
