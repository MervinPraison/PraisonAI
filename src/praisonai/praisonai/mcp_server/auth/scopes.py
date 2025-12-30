"""
MCP Scope Management

Implements incremental scope handling per MCP 2025-11-25 specification.

Features:
- Scope validation and enforcement
- WWW-Authenticate challenges for scope escalation
- Scope hierarchy support
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# Standard MCP scopes
MCP_SCOPES = {
    "tools:read": "Read tool definitions",
    "tools:call": "Execute tools",
    "resources:read": "Read resources",
    "resources:subscribe": "Subscribe to resource changes",
    "prompts:read": "Read prompts",
    "prompts:execute": "Execute prompts",
    "sampling:create": "Create sampling requests",
    "tasks:read": "Read tasks",
    "tasks:write": "Create and manage tasks",
    "admin": "Administrative access",
}


@dataclass
class ScopeChallenge:
    """
    Scope challenge for incremental consent.
    
    Used when an operation requires additional scopes.
    """
    required_scopes: List[str]
    granted_scopes: List[str]
    missing_scopes: List[str]
    error: str = "insufficient_scope"
    error_description: Optional[str] = None
    
    def to_www_authenticate(self, realm: Optional[str] = None) -> str:
        """Generate WWW-Authenticate header value."""
        parts = ["Bearer"]
        params = []
        
        if realm:
            params.append(f'realm="{realm}"')
        
        if self.missing_scopes:
            params.append(f'scope="{" ".join(self.missing_scopes)}"')
        
        params.append(f'error="{self.error}"')
        
        if self.error_description:
            params.append(f'error_description="{self.error_description}"')
        
        if params:
            parts.append(", ".join(params))
        
        return " ".join(parts)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "required_scopes": self.required_scopes,
            "granted_scopes": self.granted_scopes,
            "missing_scopes": self.missing_scopes,
            "error": self.error,
            "error_description": self.error_description,
        }


class ScopeManager:
    """
    MCP Scope Manager.
    
    Handles scope validation, enforcement, and incremental consent.
    """
    
    def __init__(
        self,
        available_scopes: Optional[Dict[str, str]] = None,
        scope_hierarchy: Optional[Dict[str, List[str]]] = None,
    ):
        """
        Initialize scope manager.
        
        Args:
            available_scopes: Available scopes with descriptions
            scope_hierarchy: Scope hierarchy (parent -> children)
        """
        self._available_scopes = available_scopes or MCP_SCOPES.copy()
        self._scope_hierarchy = scope_hierarchy or {
            "admin": list(MCP_SCOPES.keys()),
            "tools:call": ["tools:read"],
            "resources:subscribe": ["resources:read"],
            "tasks:write": ["tasks:read"],
        }
    
    def expand_scopes(self, scopes: List[str]) -> Set[str]:
        """
        Expand scopes based on hierarchy.
        
        Args:
            scopes: List of scopes
            
        Returns:
            Expanded set of scopes
        """
        expanded = set(scopes)
        
        for scope in scopes:
            if scope in self._scope_hierarchy:
                expanded.update(self._scope_hierarchy[scope])
        
        return expanded
    
    def validate_scopes(
        self,
        required: List[str],
        granted: List[str],
    ) -> tuple[bool, Optional[ScopeChallenge]]:
        """
        Validate that granted scopes satisfy requirements.
        
        Args:
            required: Required scopes
            granted: Granted scopes
            
        Returns:
            Tuple of (is_valid, challenge)
        """
        # Expand granted scopes
        expanded_granted = self.expand_scopes(granted)
        
        # Check each required scope
        missing = []
        for scope in required:
            if scope not in expanded_granted:
                missing.append(scope)
        
        if missing:
            return False, ScopeChallenge(
                required_scopes=required,
                granted_scopes=granted,
                missing_scopes=missing,
                error_description=f"Missing required scopes: {', '.join(missing)}",
            )
        
        return True, None
    
    def check_scope(
        self,
        scope: str,
        granted: List[str],
    ) -> bool:
        """
        Check if a single scope is granted.
        
        Args:
            scope: Required scope
            granted: Granted scopes
            
        Returns:
            True if scope is granted
        """
        expanded = self.expand_scopes(granted)
        return scope in expanded
    
    def get_scope_description(self, scope: str) -> Optional[str]:
        """Get description for a scope."""
        return self._available_scopes.get(scope)
    
    def list_available_scopes(self) -> Dict[str, str]:
        """List all available scopes with descriptions."""
        return self._available_scopes.copy()
    
    def add_scope(self, scope: str, description: str) -> None:
        """Add a custom scope."""
        self._available_scopes[scope] = description
    
    def add_hierarchy(self, parent: str, children: List[str]) -> None:
        """Add scope hierarchy."""
        if parent in self._scope_hierarchy:
            self._scope_hierarchy[parent].extend(children)
        else:
            self._scope_hierarchy[parent] = children


@dataclass
class ScopeRequirement:
    """Scope requirement for an operation."""
    scopes: List[str]
    any_of: bool = False  # If True, any scope is sufficient
    description: Optional[str] = None
    
    def check(self, granted: List[str], manager: ScopeManager) -> tuple[bool, Optional[ScopeChallenge]]:
        """Check if requirement is satisfied."""
        if self.any_of:
            # Any scope is sufficient
            for scope in self.scopes:
                if manager.check_scope(scope, granted):
                    return True, None
            
            return False, ScopeChallenge(
                required_scopes=self.scopes,
                granted_scopes=granted,
                missing_scopes=self.scopes,
                error_description=f"Requires one of: {', '.join(self.scopes)}",
            )
        else:
            # All scopes required
            return manager.validate_scopes(self.scopes, granted)


# Operation to scope mapping
OPERATION_SCOPES: Dict[str, ScopeRequirement] = {
    "tools/list": ScopeRequirement(["tools:read"]),
    "tools/call": ScopeRequirement(["tools:call"]),
    "resources/list": ScopeRequirement(["resources:read"]),
    "resources/read": ScopeRequirement(["resources:read"]),
    "resources/subscribe": ScopeRequirement(["resources:subscribe"]),
    "prompts/list": ScopeRequirement(["prompts:read"]),
    "prompts/get": ScopeRequirement(["prompts:read"]),
    "sampling/createMessage": ScopeRequirement(["sampling:create"]),
    "tasks/create": ScopeRequirement(["tasks:write"]),
    "tasks/get": ScopeRequirement(["tasks:read"]),
    "tasks/list": ScopeRequirement(["tasks:read"]),
    "tasks/cancel": ScopeRequirement(["tasks:write"]),
}


def get_operation_scopes(operation: str) -> Optional[ScopeRequirement]:
    """Get scope requirement for an operation."""
    return OPERATION_SCOPES.get(operation)


def require_scope(*scopes: str, any_of: bool = False):
    """
    Decorator to require scopes for a function.
    
    Args:
        scopes: Required scopes
        any_of: If True, any scope is sufficient
        
    Returns:
        Decorator function
    """
    requirement = ScopeRequirement(list(scopes), any_of=any_of)
    
    def decorator(func):
        func._scope_requirement = requirement
        return func
    
    return decorator
