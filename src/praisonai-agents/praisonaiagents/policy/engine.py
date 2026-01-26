"""
Policy Engine for PraisonAI Agents.

Manages and evaluates policies for execution control.
"""

import logging
from typing import Optional, List, Dict, Any

from .types import PolicyAction, PolicyResult
from .policy import Policy, PolicyRule
from .config import PolicyConfig

logger = logging.getLogger(__name__)


class PolicyEngine:
    """
    Policy Engine for execution control.
    
    Manages policies and evaluates them against resources
    to determine what actions are allowed.
    
    Example:
        engine = PolicyEngine()
        
        # Add a policy to block delete operations
        engine.add_policy(Policy(
            name="no_delete",
            rules=[
                PolicyRule(
                    action=PolicyAction.DENY,
                    resource="tool:delete_*",
                    reason="Delete operations are not allowed"
                )
            ]
        ))
        
        # Check if action is allowed
        result = engine.check("tool:delete_file", {})
        if not result.allowed:
            print(f"Denied: {result.reason}")
    """
    
    def __init__(self, config: Optional[PolicyConfig] = None):
        """
        Initialize the policy engine.
        
        Args:
            config: Engine configuration
        """
        self.config = config or PolicyConfig()
        self._policies: Dict[str, Policy] = {}
    
    @property
    def policies(self) -> List[Policy]:
        """Get all policies sorted by priority."""
        return sorted(
            self._policies.values(),
            key=lambda p: p.priority,
            reverse=True
        )
    
    def add_policy(self, policy: Policy):
        """
        Add a policy to the engine.
        
        Args:
            policy: Policy to add
        """
        self._policies[policy.name] = policy
        logger.debug(f"Added policy: {policy.name}")
    
    def remove_policy(self, name: str) -> bool:
        """
        Remove a policy by name.
        
        Args:
            name: Policy name
            
        Returns:
            True if removed, False if not found
        """
        if name in self._policies:
            del self._policies[name]
            logger.debug(f"Removed policy: {name}")
            return True
        return False
    
    def get_policy(self, name: str) -> Optional[Policy]:
        """Get a policy by name."""
        return self._policies.get(name)
    
    def enable_policy(self, name: str) -> bool:
        """Enable a policy."""
        policy = self._policies.get(name)
        if policy:
            policy.enabled = True
            return True
        return False
    
    def disable_policy(self, name: str) -> bool:
        """Disable a policy."""
        policy = self._policies.get(name)
        if policy:
            policy.enabled = False
            return True
        return False
    
    def check(
        self,
        resource: str,
        context: Optional[Dict[str, Any]] = None
    ) -> PolicyResult:
        """
        Check if an action is allowed.
        
        Args:
            resource: Resource identifier (e.g., "tool:read_file")
            context: Additional context for policy evaluation
            
        Returns:
            PolicyResult indicating if action is allowed
        """
        if not self.config.enabled:
            return PolicyResult.allow("Policy engine disabled")
        
        context = context or {}
        
        # Evaluate policies in priority order
        for policy in self.policies:
            result = policy.evaluate(resource, context)
            if result is not None:
                if self.config.log_decisions:
                    logger.info(
                        f"Policy decision: {result.action.value} for {resource} "
                        f"(policy: {result.policy_name}, reason: {result.reason})"
                    )
                return result
        
        # No policy matched - use default action
        if self.config.strict_mode:
            return PolicyResult.deny(
                "No policy matched and strict mode is enabled"
            )
        
        return PolicyResult.allow("No policy matched")
    
    def check_tool(
        self,
        tool_name: str,
        tool_input: Optional[Dict[str, Any]] = None
    ) -> PolicyResult:
        """
        Check if a tool execution is allowed.
        
        Args:
            tool_name: Name of the tool
            tool_input: Tool input parameters
            
        Returns:
            PolicyResult
        """
        return self.check(
            f"tool:{tool_name}",
            {"tool_name": tool_name, "tool_input": tool_input or {}}
        )
    
    def check_file(
        self,
        operation: str,
        file_path: str
    ) -> PolicyResult:
        """
        Check if a file operation is allowed.
        
        Args:
            operation: Operation type (read, write, delete)
            file_path: Path to the file
            
        Returns:
            PolicyResult
        """
        return self.check(
            f"file:{operation}",
            {"operation": operation, "file_path": file_path}
        )
    
    def clear(self):
        """Remove all policies."""
        self._policies.clear()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert engine state to dictionary."""
        return {
            "config": {
                "enabled": self.config.enabled,
                "default_action": self.config.default_action,
                "strict_mode": self.config.strict_mode
            },
            "policies": [p.to_dict() for p in self.policies]
        }
    
    def load_from_dict(self, data: Dict[str, Any]):
        """Load policies from a dictionary."""
        for policy_data in data.get("policies", []):
            policy = Policy.from_dict(policy_data)
            self.add_policy(policy)
    
    def load_from_yaml(self, filepath: str) -> None:
        """Load policies from a YAML file.
        
        Args:
            filepath: Path to YAML policy file
            
        Raises:
            ImportError: If PyYAML is not installed
            FileNotFoundError: If the file doesn't exist
            ValueError: If the YAML is malformed or invalid
            
        Example YAML format:
            policies:
              - name: deny_shell
                priority: 100
                rules:
                  - match: "tool:shell_*"
                    action: deny
                    reason: "Shell tools disabled"
        """
        try:
            import yaml
        except ImportError:
            raise ImportError(
                "PyYAML is required for YAML policy loading. "
                "Install with: pip install pyyaml"
            )
        
        import os
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Policy file not found: {filepath}")
        
        try:
            with open(filepath, 'r') as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in policy file: {e}")
        
        if data is None:
            raise ValueError("Policy file is empty")
        
        if not isinstance(data, dict):
            raise ValueError("Policy file must contain a YAML dictionary")
        
        self.load_from_dict(data)


# Convenience functions for common policies

def create_deny_tools_policy(
    tool_patterns: List[str],
    name: str = "deny_tools",
    reason: str = "Tool not allowed"
) -> Policy:
    """
    Create a policy that denies specific tools.
    
    Args:
        tool_patterns: List of tool name patterns to deny
        name: Policy name
        reason: Reason for denial
        
    Returns:
        Policy
    """
    rules = [
        PolicyRule(
            action=PolicyAction.DENY,
            resource=f"tool:{pattern}",
            reason=reason,
            name=f"deny_{pattern}"
        )
        for pattern in tool_patterns
    ]
    
    return Policy(name=name, rules=rules)


def create_allow_tools_policy(
    tool_patterns: List[str],
    name: str = "allow_tools"
) -> Policy:
    """
    Create a policy that allows specific tools.
    
    Args:
        tool_patterns: List of tool name patterns to allow
        name: Policy name
        
    Returns:
        Policy
    """
    rules = [
        PolicyRule(
            action=PolicyAction.ALLOW,
            resource=f"tool:{pattern}",
            name=f"allow_{pattern}"
        )
        for pattern in tool_patterns
    ]
    
    return Policy(name=name, rules=rules, priority=10)


def create_read_only_policy(name: str = "read_only") -> Policy:
    """
    Create a read-only policy that denies write operations.
    
    Args:
        name: Policy name
        
    Returns:
        Policy
    """
    return Policy(
        name=name,
        rules=[
            PolicyRule(
                action=PolicyAction.DENY,
                resource="file:write",
                reason="Write operations not allowed in read-only mode",
                name="deny_write"
            ),
            PolicyRule(
                action=PolicyAction.DENY,
                resource="file:delete",
                reason="Delete operations not allowed in read-only mode",
                name="deny_delete"
            ),
            PolicyRule(
                action=PolicyAction.DENY,
                resource="tool:*_write*",
                reason="Write tools not allowed in read-only mode",
                name="deny_write_tools"
            ),
            PolicyRule(
                action=PolicyAction.DENY,
                resource="tool:*_delete*",
                reason="Delete tools not allowed in read-only mode",
                name="deny_delete_tools"
            ),
        ],
        priority=100
    )
