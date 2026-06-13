"""Runtime configuration system for PraisonAI Agents.

Provides model-scoped runtime selection following the protocol-driven design:
- Core protocols and dataclasses in this module
- Heavy implementations in wrapper layer (praisonai package)
- Fail-closed behavior for unknown runtime IDs
"""

def __getattr__(name: str):
    """Lazy loading for runtime components."""
    if name == "AgentRuntimeConfig":
        from .config import AgentRuntimeConfig
        return AgentRuntimeConfig
    elif name == "RuntimeRegistry":
        from .registry import RuntimeRegistry
        return RuntimeRegistry
    elif name == "RuntimeResolver":
        from .resolver import RuntimeResolver
        return RuntimeResolver
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = [
    "AgentRuntimeConfig",
    "RuntimeRegistry",
    "RuntimeResolver"
]