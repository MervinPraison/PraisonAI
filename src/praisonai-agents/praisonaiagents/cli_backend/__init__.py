"""CLI Backend Protocol for PraisonAI Agents.

Provides protocol-driven core for integrating external CLI tools as agent backends.

This module follows AGENTS.md protocol-driven design:
- Core SDK contains only protocols and dataclasses
- Heavy implementations live in wrapper (praisonai package)
- Zero optional dependencies at import time
"""

def __getattr__(name: str):
    """Lazy loading for CLI backend components."""
    if name == "CliBackendProtocol":
        from .protocols import CliBackendProtocol
        return CliBackendProtocol
    elif name == "CliBackendConfig":
        from .protocols import CliBackendConfig
        return CliBackendConfig
    elif name == "CliSessionBinding":
        from .protocols import CliSessionBinding
        return CliSessionBinding
    elif name == "CliBackendResult":
        from .protocols import CliBackendResult
        return CliBackendResult
    elif name == "CliBackendDelta":
        from .protocols import CliBackendDelta
        return CliBackendDelta
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = [
    "CliBackendProtocol",
    "CliBackendConfig", 
    "CliSessionBinding",
    "CliBackendResult",
    "CliBackendDelta"
]