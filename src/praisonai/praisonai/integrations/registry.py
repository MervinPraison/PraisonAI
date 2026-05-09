"""
External Agent Registry for PraisonAI.

Provides a registry pattern for managing external CLI integrations,
allowing dynamic registration and discovery of external agents.

Features:
- Dynamic registration of custom integrations
- Availability checking for all registered integrations
- Factory pattern for creating integrations
- Backward compatibility with existing get_available_integrations()

Usage:
    from praisonai.integrations.registry import get_default_registry
    
    # Get default registry (or inject custom for multi-tenant)
    registry = get_default_registry()
    
    # Register custom integration
    registry.register('my-agent', MyCustomIntegration)
    
    # Create integration
    agent = registry.create('claude', workspace="/path/to/project")
    
    # List available integrations
    available = await registry.get_available()
"""

import threading
from typing import Dict, Type, Optional, Any, List

from .base import BaseCLIIntegration
from .._registry import PluginRegistry


def _claude_code_loader():
    from .claude_code import ClaudeCodeIntegration
    return ClaudeCodeIntegration

def _gemini_cli_loader():
    from .gemini_cli import GeminiCLIIntegration
    return GeminiCLIIntegration

def _codex_cli_loader():
    from .codex_cli import CodexCLIIntegration
    return CodexCLIIntegration

def _cursor_cli_loader():
    from .cursor_cli import CursorCLIIntegration
    return CursorCLIIntegration

# Built-in external agent integrations with lazy loading
_BUILTIN_INTEGRATIONS = {
    "claude": _claude_code_loader,
    "gemini": _gemini_cli_loader,
    "codex": _codex_cli_loader,
    "cursor": _cursor_cli_loader,
}


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
        
    def create(self, name: str, **kwargs: Any) -> Optional[BaseCLIIntegration]:
        """
        Create an instance of the specified integration.
        
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
                import logging
                logging.warning(f"Failed to check availability for {name}: {e}")
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
    return registry.create(name, **kwargs)


def get_available_integrations() -> Dict[str, bool]:
    """
    Get availability status of all registered integrations.
    
    Backward compatibility wrapper for the original synchronous function.
    
    Returns:
        Dict[str, bool]: Mapping of integration name to availability status
    """
    import asyncio
    registry = get_default_registry()
    
    from .._async_bridge import run_sync
    return run_sync(registry.get_available())