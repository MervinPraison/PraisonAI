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


from .._lazy import create_lazy_getattr

_LAZY_IMPORTS = {
    "PolicyEngine": (f"{__name__}.engine", "PolicyEngine"),
    "Policy": (f"{__name__}.policy", "Policy"),
    "PolicyRule": (f"{__name__}.policy", "PolicyRule"),
    "PolicyResult": (f"{__name__}.types", "PolicyResult"),
    "PolicyAction": (f"{__name__}.types", "PolicyAction"),
    "PolicyConfig": (f"{__name__}.config", "PolicyConfig"),
    "create_deny_tools_policy": (f"{__name__}.engine", "create_deny_tools_policy"),
    "create_allow_tools_policy": (f"{__name__}.engine", "create_allow_tools_policy"),
    "create_read_only_policy": (f"{__name__}.engine", "create_read_only_policy"),
}

__getattr__ = create_lazy_getattr(_LAZY_IMPORTS, __name__)
