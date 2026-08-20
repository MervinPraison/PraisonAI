"""
External Agent Registry for PraisonAI.

Provides a registry pattern for managing external CLI integrations,
allowing dynamic registration and discovery of external agents.

Features:
- Dynamic registration of custom integrations
- Availability checking for all registered integrations
- Factory pattern for creating integrations

Usage:
    from praisonai.integrations.registry import get_default_registry
    
    # Get default registry (or inject custom for multi-tenant)
    registry = get_default_registry()
    
    # Register custom integration
    registry.register('my-agent', MyCustomIntegration)
    
    # Create integration (use try_create for optional behavior)
    agent = registry.try_create('claude', workspace="/path/to/project")
    if agent is None:
        print("Integration 'claude' not found or unavailable")
    
    # List available integrations
    available = await registry.get_available()
"""

import logging
import threading
from typing import Dict, Type, Optional, Any, List

from .base import BaseCLIIntegration
from .._registry import PluginRegistry
from ._cli_loaders import BUILTIN_INTEGRATIONS as _BUILTIN_INTEGRATIONS

logger = logging.getLogger(__name__)


class ExternalAgentRegistry(PluginRegistry[BaseCLIIntegration]):
    """
    Registry for external CLI integrations.
    
    Provides centralized management of external agent integrations
    with support for dynamic registration and availability checking.
    
    Uses dependency injection pattern instead of singleton.
    """
    
    def __init__(self):
        """Initialize the registry with built-in integrations."""
        super().__init__(
            entry_point_group="praisonai.external_agents", 
            builtins=_BUILTIN_INTEGRATIONS
        )
        # Built-ins must win: a third-party distribution publishing "claude"
        # must not be able to replace the shipped ClaudeCodeIntegration. This is
        # now enforced once in the base PluginRegistry (see #4171), so no local
        # re-assertion is needed here — a plugin may add new names, never replace
        # a shipped one.
    
    def register(self, name: str, integration_class: Type[BaseCLIIntegration]) -> None:
        """
        Register a new external agent integration.
        
        Args:
            name: Unique name for the integration
            integration_class: The integration class (must inherit from BaseCLIIntegration)
            
        Raises:
            ValueError: If integration_class does not inherit from BaseCLIIntegration
        """
        if not issubclass(integration_class, BaseCLIIntegration):
            raise ValueError(
                f"Integration class {integration_class.__name__} must inherit from BaseCLIIntegration"
            )
        
        # Delegate to parent
        super().register(name, integration_class)
    
    # Backward compatibility methods
    def list_registered(self) -> List[str]:
        """
        List all registered integration names.
        
        Returns:
            List[str]: List of registered integration names
        """
        return self.list_names()
        
    def try_create(self, name: str, **kwargs: Any) -> Optional[BaseCLIIntegration]:
        """
        Try to create an instance of the specified integration.
        
        Args:
            name: Name of the integration
            **kwargs: Arguments to pass to the integration constructor
            
        Returns:
            BaseCLIIntegration: Instance of the integration, or None if not found
        """
        try:
            return super().create(name, **kwargs)
        except ValueError:
            return None
    
    async def get_available(self) -> Dict[str, bool]:
        """
        Get availability status of all registered integrations.
        
        Returns:
            Dict[str, bool]: Mapping of integration name to availability status
        """
        import inspect
        availability = {}
        
        # Get snapshot of all items from parent class
        with self._lock:
            snapshot = list(self._items.items())
        
        for name, integration_class in snapshot:
            try:
                # Check if constructor requires parameters beyond self
                sig = inspect.signature(integration_class.__init__)
                params = [p for p_name, p in sig.parameters.items() if p_name != 'self' and p.default is inspect.Parameter.empty]
                
                if params:
                    # Constructor requires arguments, can't instantiate for availability check
                    # Skip this integration rather than marking it unavailable
                    continue
                
                # Create a temporary instance to check availability
                instance = integration_class()
                availability[name] = instance.is_available
            except Exception as e:
                # Log real exceptions rather than hiding them
                logger.warning("Failed to check availability for %s: %s", name, e)
                availability[name] = False
        
        return availability
    
    async def get_available_names(self) -> List[str]:
        """
        Get names of all available integrations.
        
        Returns:
            List[str]: List of available integration names
        """
        availability = await self.get_available()
        return [name for name, available in availability.items() if available]


# Default registry (lazy, module-private). NOT exposed as a singleton getter.
_default_registry: Optional[ExternalAgentRegistry] = None
_default_lock = threading.Lock()


def get_default_registry() -> ExternalAgentRegistry:
    """Return the process-default registry. Prefer DI; use this only at the edge.""" 
    global _default_registry
    if _default_registry is None:
        with _default_lock:
            if _default_registry is None:
                _default_registry = ExternalAgentRegistry()
    return _default_registry


# Factory functions for convenient access - using default registry
def get_registry() -> ExternalAgentRegistry:
    """
    Get the default external agent registry.
    
    Returns:
        ExternalAgentRegistry: The default registry instance
    """
    return get_default_registry()


def register_integration(name: str, integration_class: Type[BaseCLIIntegration]) -> None:
    """
    Register a new external agent integration.
    
    Args:
        name: Unique name for the integration
        integration_class: The integration class (must inherit from BaseCLIIntegration)
    """
    registry = get_default_registry()
    registry.register(name, integration_class)


def create_integration(name: str, **kwargs: Any) -> Optional[BaseCLIIntegration]:
    """
    Create an instance of the specified integration.
    
    Args:
        name: Name of the integration
        **kwargs: Arguments to pass to the integration constructor
        
    Returns:
        BaseCLIIntegration: Instance of the integration, or None if not found
    """
    registry = get_default_registry()
    return registry.try_create(name, **kwargs)


def list_external_agents() -> List[str]:
    """Names of every *usable* external agent (built-ins + plugins).

    This is the single source of truth for every surface that has to *list*
    external agents: the ``--external-agent`` argparse choices, the CLI
    handler and the UI settings toggles. Do not hand-maintain a second copy.

    Derived from :func:`external_agent_catalog` so the argparse ``choices`` can
    never advertise a name the handler then rejects: a plugin that fails to
    load is dropped from the catalog and therefore never offered in ``--help``.

    Built-ins keep their declaration order (claude, gemini, codex, cursor) so
    help text and UI toggles are unchanged on a default install; plugins are
    appended in sorted order behind them.
    """
    names = set(external_agent_catalog())
    ordered = [n for n in _BUILTIN_INTEGRATIONS if n in names]
    ordered += sorted(names.difference(ordered))
    return ordered


def external_agent_catalog() -> Dict[str, Dict[str, Any]]:
    """Presentation metadata for every registered external agent.

    Returns a mapping of registered name -> ``{"cls", "label", "cli", "install"}``.
    ``cli`` is the executable probed for availability; it falls back to the
    registered name when the integration cannot be introspected (for example a
    third-party class whose constructor needs arguments).
    """
    registry = get_default_registry()
    catalog: Dict[str, Dict[str, Any]] = {}
    # Iterate registered *names* directly. Do NOT call ``list_external_agents``
    # here: that would recurse (it is now derived from this catalog).
    names = set(registry.list_names())
    ordered = [n for n in _BUILTIN_INTEGRATIONS if n in names]
    ordered += sorted(names.difference(ordered))
    for name in ordered:
        try:
            cls = registry.resolve(name)
        except Exception as exc:  # noqa: BLE001 - isolate faulty optional plugins
            # A third-party entry point may raise anything (not just ValueError)
            # while loading. One broken optional plugin must not blank out the
            # catalog for every surface (argparse/CLI/UI); skip it and log.
            logger.warning("Skipping external agent %r: failed to load (%s)", name, exc)
            continue
        try:
            cli = cls().cli_command
        except Exception:  # noqa: BLE001 - metadata must never break listing
            cli = name
        catalog[name] = {
            "cls": cls,
            "label": getattr(cls, "display_label", None) or f"{name} CLI",
            "cli": cli,
            "install": getattr(cls, "install_hint", None) or "See documentation",
        }
    return catalog