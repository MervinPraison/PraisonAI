"""
Framework Adapter Registry for PraisonAI.

Provides a registry pattern for managing framework adapters with entry points support,
enabling dynamic registration and discovery of framework adapters.
Uses dependency injection instead of singleton pattern.
"""

from __future__ import annotations

from typing import Dict, Type, Optional
import inspect
import logging

from .base import FrameworkAdapter
from .._registry import PluginRegistry

logger = logging.getLogger(__name__)


def _crewai_loader():
    from .crewai_adapter import CrewAIAdapter
    return CrewAIAdapter

def _autogen_loader():
    from .autogen_adapter import AutoGenAdapter
    return AutoGenAdapter

def _autogen_v4_loader():
    from .autogen_adapter import AutoGenV4Adapter
    return AutoGenV4Adapter

def _ag2_loader():
    from .autogen_adapter import AG2Adapter
    return AG2Adapter

def _praisonai_loader():
    from .praisonai_adapter import PraisonAIAdapter
    return PraisonAIAdapter

# Built-in framework adapters with lazy loading
_BUILTIN_ADAPTERS = {
    "crewai": _crewai_loader,
    "autogen": _autogen_loader,
    "autogen_v4": _autogen_v4_loader,
    "ag2": _ag2_loader,
    "praisonai": _praisonai_loader,
}

class FrameworkAdapterRegistry(PluginRegistry[FrameworkAdapter]):
    """
    Registry for framework adapters.
    
    Provides centralized management of framework adapters with support
    for dynamic registration, entry points discovery, and availability checking.
    
    Uses dependency injection pattern instead of singleton.
    """

    def __init__(self) -> None:
        """Initialize the registry with built-in adapters."""
        super().__init__(
            entry_point_group="praisonai.framework_adapters",
            builtins=_BUILTIN_ADAPTERS
        )
    
    def _validate_adapter(self, name: str, adapter) -> None:
        """Validate that adapter implements the required protocol signature."""
        _REQUIRED_KW = {"tools_dict", "agent_callback", "task_callback", "cli_config"}
        
        sig = inspect.signature(type(adapter).run)
        kw_only = {
            p.name for p in sig.parameters.values()
            if p.kind in (inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        }
        missing = _REQUIRED_KW - kw_only
        if missing:
            raise TypeError(
                f"FrameworkAdapter {name!r} does not implement the protocol: "
                f"missing keyword-only parameters {sorted(missing)}"
            )
    
    def create(self, name: str, *args, **kwargs):
        """Create an adapter instance with protocol validation."""
        adapter = super().create(name, *args, **kwargs)
        self._validate_adapter(name, adapter)
        return adapter

    # Backward compatibility aliases - delegate to parent methods
    def list_registered(self) -> list[str]:
        """
        List all registered framework adapter names.
        
        Returns:
            list[str]: Sorted list of registered adapter names
        """
        return self.list_names()

    def is_available(self, name: str) -> bool:
        """
        Check if a framework adapter is available and functional.
        
        Args:
            name: Name of the adapter to check
            
        Returns:
            bool: True if adapter exists and is available
        """
        try:
            adapter = self.create(name)
        except (ValueError, TypeError):
            return False
        
        try:
            return adapter.is_available()
        except Exception:
            logger.warning("is_available() raised for adapter %r", name, exc_info=True)
            return False


# Default registry access - replaced by FrameworkAdapterRegistry.default()
def get_default_registry() -> FrameworkAdapterRegistry:
    """Return the process-default registry. Prefer DI; use this only at the edge."""
    return FrameworkAdapterRegistry.default()