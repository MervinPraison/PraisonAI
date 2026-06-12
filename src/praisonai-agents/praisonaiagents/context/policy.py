"""
Context Compaction Policy for PraisonAI Agents.

Protocol-driven design: This module provides compatibility exports for the 
ContextCompactionPolicy interface. The heavy implementation has been moved
to adapters.py following AGENTS.md guidelines.

Usage remains the same for backward compatibility:
    from praisonaiagents.context.policy import ContextCompactionPolicy
    policy = ContextCompactionPolicy(trigger_at=0.85)
"""

# Protocol imports (lightweight interface definitions)
from .protocols import (
    ContextCompactionPolicyProtocol,
    CompactionRoute,
    CompactionStrategy,
    ContextBudgetResult,
    get_default_policy as get_default_policy_protocol
)

# Adapter imports (heavy implementations)
from .adapters import (
    ContextCompactionPolicyAdapter,
    CONSERVATIVE_POLICY,
    BALANCED_POLICY, 
    AGGRESSIVE_POLICY,
    get_default_policy_impl
)

# Compatibility re-exports for backward compatibility
# Users can still import ContextCompactionPolicy but get the adapter implementation
ContextCompactionPolicy = ContextCompactionPolicyAdapter


def get_default_policy() -> ContextCompactionPolicyProtocol:
    """Get the default context compaction policy."""
    return get_default_policy_impl()