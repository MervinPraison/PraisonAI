"""
Exec Policy Engine for PraisonAI Agents.

Provides policy-based execution control:
- Define rules for what agents can/cannot do
- Tool execution policies
- Resource access control
- Rate limiting and quotas

Zero Performance Impact:
- All imports are lazy loaded via __getattr__
- Policies only evaluated when enabled
- No overhead when no policies defined

Usage:
    from praisonaiagents.policy import PolicyEngine, Policy, PolicyRule
    
    # Create a policy engine
    engine = PolicyEngine()
    
    # Add a policy
    policy = Policy(
        name="no_delete",
        rules=[
            PolicyRule(
                action="deny",
                resource="tool:delete_*",
                reason="Delete operations are not allowed"
            )
        ]
    )
    engine.add_policy(policy)
    
    # Check if action is allowed
    result = engine.check("tool:delete_file", context={})
"""

__all__ = [
    # Core classes
    "PolicyEngine",
    "Policy",
    "PolicyRule",
    # Result types
    "PolicyResult",
    "PolicyAction",
    # Configuration
    "PolicyConfig",
    # Convenience functions
    "create_deny_tools_policy",
    "create_allow_tools_policy",
    "create_read_only_policy",
]


def __getattr__(name: str):
    """Lazy load module components to avoid import overhead."""
    if name == "PolicyEngine":
        from .engine import PolicyEngine
        return PolicyEngine
    
    if name in ("Policy", "PolicyRule"):
        from .policy import Policy, PolicyRule
        return locals()[name]
    
    if name in ("PolicyResult", "PolicyAction"):
        from .types import PolicyResult, PolicyAction
        return locals()[name]
    
    if name == "PolicyConfig":
        from .config import PolicyConfig
        return PolicyConfig
    
    if name in ("create_deny_tools_policy", "create_allow_tools_policy", "create_read_only_policy"):
        from .engine import create_deny_tools_policy, create_allow_tools_policy, create_read_only_policy
        return locals()[name]
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
