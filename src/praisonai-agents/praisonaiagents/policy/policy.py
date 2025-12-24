"""
Policy and PolicyRule for PraisonAI Agents.

Defines policies and rules for execution control.
"""

import re
import fnmatch
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable

from .types import PolicyAction, PolicyResult


@dataclass
class PolicyRule:
    """
    A single rule within a policy.
    
    Rules match against resources and contexts to determine
    what action to take.
    """
    action: PolicyAction
    resource: Optional[str] = None  # Pattern to match (supports wildcards)
    condition: Optional[Callable[[Dict[str, Any]], bool]] = None
    reason: Optional[str] = None
    name: Optional[str] = None
    priority: int = 0  # Higher priority rules are evaluated first
    
    def matches(self, resource: str, context: Dict[str, Any]) -> bool:
        """
        Check if this rule matches the given resource and context.
        
        Args:
            resource: Resource identifier (e.g., "tool:read_file")
            context: Additional context for the check
            
        Returns:
            True if the rule matches
        """
        # Check resource pattern
        if self.resource:
            if not self._match_pattern(self.resource, resource):
                return False
        
        # Check condition
        if self.condition:
            try:
                if not self.condition(context):
                    return False
            except Exception:
                return False
        
        return True
    
    def _match_pattern(self, pattern: str, value: str) -> bool:
        """Match a pattern against a value (supports wildcards)."""
        # Convert glob pattern to regex
        if "*" in pattern or "?" in pattern:
            return fnmatch.fnmatch(value, pattern)
        return pattern == value
    
    def evaluate(self, resource: str, context: Dict[str, Any]) -> Optional[PolicyResult]:
        """
        Evaluate this rule against a resource.
        
        Args:
            resource: Resource identifier
            context: Additional context
            
        Returns:
            PolicyResult if rule matches, None otherwise
        """
        if not self.matches(resource, context):
            return None
        
        return PolicyResult(
            allowed=self.action in (PolicyAction.ALLOW, PolicyAction.LOG),
            action=self.action,
            rule_name=self.name,
            reason=self.reason
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "action": self.action.value,
            "resource": self.resource,
            "reason": self.reason,
            "name": self.name,
            "priority": self.priority
        }


@dataclass
class Policy:
    """
    A collection of rules that define execution policy.
    
    Policies are evaluated in order, with higher priority rules
    taking precedence.
    """
    name: str
    rules: List[PolicyRule] = field(default_factory=list)
    description: Optional[str] = None
    enabled: bool = True
    priority: int = 0  # Higher priority policies are evaluated first
    
    def add_rule(self, rule: PolicyRule):
        """Add a rule to this policy."""
        self.rules.append(rule)
        # Sort by priority (descending)
        self.rules.sort(key=lambda r: r.priority, reverse=True)
    
    def remove_rule(self, rule_name: str) -> bool:
        """Remove a rule by name."""
        for i, rule in enumerate(self.rules):
            if rule.name == rule_name:
                self.rules.pop(i)
                return True
        return False
    
    def evaluate(self, resource: str, context: Dict[str, Any]) -> Optional[PolicyResult]:
        """
        Evaluate this policy against a resource.
        
        Args:
            resource: Resource identifier
            context: Additional context
            
        Returns:
            PolicyResult if any rule matches, None otherwise
        """
        if not self.enabled:
            return None
        
        for rule in self.rules:
            result = rule.evaluate(resource, context)
            if result is not None:
                result.policy_name = self.name
                return result
        
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "priority": self.priority,
            "rules": [r.to_dict() for r in self.rules]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Policy":
        """Create a policy from a dictionary."""
        rules = []
        for rule_data in data.get("rules", []):
            rules.append(PolicyRule(
                action=PolicyAction(rule_data["action"]),
                resource=rule_data.get("resource"),
                reason=rule_data.get("reason"),
                name=rule_data.get("name"),
                priority=rule_data.get("priority", 0)
            ))
        
        return cls(
            name=data["name"],
            rules=rules,
            description=data.get("description"),
            enabled=data.get("enabled", True),
            priority=data.get("priority", 0)
        )
