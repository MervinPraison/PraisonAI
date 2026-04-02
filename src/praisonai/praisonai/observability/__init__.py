"""
PraisonAI Observability Integrations.

Observability adapters for external platforms like Langfuse, WandB, etc.
These live in the wrapper layer and implement TraceSinkProtocol from the core SDK.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .langfuse import LangfuseSink, LangfuseSinkConfig

__all__ = []

def __getattr__(name: str):
    """Lazy imports for optional observability dependencies."""
    if name == "LangfuseSink":
        from .langfuse import LangfuseSink
        return LangfuseSink
    elif name == "LangfuseSinkConfig":
        from .langfuse import LangfuseSinkConfig
        return LangfuseSinkConfig
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")