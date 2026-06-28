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
    from .autogen_adapter import AutoGenFamilyAdapter
    return AutoGenFamilyAdapter

def _autogen_v2_loader():
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

# Built-in framework adapters with lazy loading.
# autogen_v4 / ag2 loaders remain for entry-point packages; not registered until implemented.
_BUILTIN_ADAPTERS = {
    "crewai": _crewai_loader,
    "autogen": _autogen_loader,       # Family adapter for version resolution
    "autogen_v2": _autogen_v2_loader,  # Direct access to v0.2
    "praisonai": _praisonai_loader,
}

class FrameworkAdapterRegistry(PluginRegistry[FrameworkAdapter]):
    """
    Registry for framework adapters.
    
    Provides centralized management of framework adapters with support
    for dynamic registration, entry points discovery, and availability checking.
    
    Uses dependency injection pattern instead of singleton.
    """

    # Default selection priority used when no framework is requested
    # explicitly. Entry-point plugins registered under the
    # ``praisonai.framework_adapters`` group are consulted after this list,
    # so a third-party adapter can become the default once the built-ins are
    # unavailable.
    DEFAULT_PRIORITY: tuple[str, ...] = ("crewai", "praisonai", "autogen", "ag2")

    def __init__(self) -> None:
        """Initialize the registry with built-in adapters."""
        super().__init__(
            entry_point_group="praisonai.framework_adapters",
            builtins=_BUILTIN_ADAPTERS
        )

    def pick_default(self) -> str:
        """Return the name of the default framework to use.

        Resolution policy (single source of truth for default selection):

        1. Walk ``DEFAULT_PRIORITY`` and return the first available adapter.
        2. Fall back to any other registered adapter (e.g. entry-point
           plugins) that reports availability.

        Returns:
            str: Name of the first available framework adapter.

        Raises:
            RuntimeError: If no registered adapter is available.
        """
        for name in self.DEFAULT_PRIORITY:
            try:
                if self.is_available(name):
                    return name
            except (ValueError, TypeError):
                continue

        # Entry-point / runtime-registered adapters get a chance to be the
        # default once none of the built-in priorities are installed.
        for name in self.list_names():
            if name in self.DEFAULT_PRIORITY:
                continue
            try:
                if self.is_available(name):
                    return name
            except (ValueError, TypeError):
                continue

        raise RuntimeError(
            "No supported framework installed. Available adapters: "
            f"{self.list_all_names()}"
        )
    
    def _validate_adapter(self, name: str, adapter) -> None:
        """Validate that adapter implements the required protocol signature."""
        if getattr(adapter, "is_router", False):
            return

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

    def list_available_frameworks(self) -> list[str]:
        """Return registered framework names that report availability."""
        return sorted(
            name for name in self.list_names() if self.is_available(name)
        )

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


def list_framework_choices(*, include_unavailable: bool = False) -> list[str]:
    """Single source of truth for CLI/YAML framework name lists.

    Discovers built-in adapters *and* third-party adapters registered via the
    ``praisonai.framework_adapters`` entry-point group, so newly installed
    adapters appear automatically wherever framework names are shown or
    validated (argparse ``choices``, doctor checks, etc.).

    Args:
        include_unavailable: When True, return every registered adapter name;
            otherwise only those reporting availability.

    Returns:
        Sorted list of framework adapter names.
    """
    registry = get_default_registry()
    if include_unavailable:
        return sorted(registry.list_names())
    return registry.list_available_frameworks()


def list_available_frameworks() -> list[str]:
    """Return registered framework names that report availability."""
    return get_default_registry().list_available_frameworks()


def get_install_hint(name: str) -> str:
    """Return install hint for a framework, consulting the adapter when registered.

    Falls back to ``pip install 'praisonai[<extra>]'`` when the adapter cannot
    be resolved (e.g. its dependencies are missing) or does not declare a hint.
    """
    registry = get_default_registry()
    try:
        adapter = registry.create(name)
        hint = getattr(adapter, "install_hint", None)
        if hint:
            return hint
    except (ValueError, TypeError, ImportError):
        pass
    extra_name = {"autogen_v4": "autogen-v4"}.get(name, name)
    return f"pip install 'praisonai[{extra_name}]'"


def framework_option_help() -> str:
    """Help text for CLI --framework options (registry-driven)."""
    try:
        names = list_framework_choices(include_unavailable=True)
    except ImportError:
        return "Framework: praisonai, crewai, autogen"
    if names:
        return "Framework: " + ", ".join(names)
    return "Framework: praisonai, crewai, autogen"
