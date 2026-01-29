"""
Permissions Module for PraisonAI Agents.

Provides pattern-based permission rules, persistent approvals,
and doom loop detection for safe agent execution.

Features:
- Pattern-based permission rules (allow, deny, ask)
- Persistent approval storage
- Per-agent permission rulesets
- Doom loop detection and prevention
- Integration with existing approval system

Usage:
    from praisonaiagents.permissions import PermissionManager, PermissionRule
    
    # Create permission manager
    manager = PermissionManager()
    
    # Add rules
    manager.add_rule(PermissionRule(
        pattern="bash:*",
        action="ask",
        description="Require approval for shell commands"
    ))
    
    # Check permission
    result = manager.check("bash:rm -rf /tmp/test")
"""

__all__ = [
    "PermissionManager",
    "PermissionRule",
    "PermissionAction",
    "PermissionMode",
    "PermissionResult",
    "DoomLoopDetector",
]


def __getattr__(name: str):
    """Lazy load module components."""
    if name == "PermissionManager":
        from .manager import PermissionManager
        return PermissionManager
    
    if name == "PermissionRule":
        from .rules import PermissionRule
        return PermissionRule
    
    if name == "PermissionAction":
        from .rules import PermissionAction
        return PermissionAction
    
    if name == "PermissionMode":
        from .rules import PermissionMode
        return PermissionMode
    
    if name == "PermissionResult":
        from .rules import PermissionResult
        return PermissionResult
    
    if name == "DoomLoopDetector":
        from .doom_loop import DoomLoopDetector
        return DoomLoopDetector
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
