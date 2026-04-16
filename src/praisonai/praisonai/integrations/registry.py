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
    from praisonai.integrations.registry import ExternalAgentRegistry
    
    # Get singleton registry
    registry = ExternalAgentRegistry.get_instance()
    
    # Register custom integration
    registry.register('my-agent', MyCustomIntegration)
    
    # Create integration
    agent = registry.create('claude', workspace="/path/to/project")
    
    # List available integrations
    available = await registry.get_available()
"""

from typing import Dict, Type, Optional, Any, List
from abc import ABC

from .base import BaseCLIIntegration


class ExternalAgentRegistry:
    """
    Registry for external CLI integrations.
    
    Provides centralized management of external agent integrations
    with support for dynamic registration and availability checking.
    
    Uses singleton pattern to ensure consistent state across the application.
    """
    
    _instance: Optional['ExternalAgentRegistry'] = None
    
    def __init__(self):
        """Initialize the registry with built-in integrations."""
        self._integrations: Dict[str, Type[BaseCLIIntegration]] = {}
        self._register_builtin_integrations()
    
    @classmethod
    def get_instance(cls) -> 'ExternalAgentRegistry':
        """
        Get the singleton registry instance.
        
        Returns:
            ExternalAgentRegistry: The singleton registry
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def _register_builtin_integrations(self):
        """Register built-in integrations."""
        # Lazy imports to avoid circular dependencies and performance impact
        try:
            from .claude_code import ClaudeCodeIntegration
            self._integrations['claude'] = ClaudeCodeIntegration
        except ImportError:
            pass
        
        try:
            from .gemini_cli import GeminiCLIIntegration
            self._integrations['gemini'] = GeminiCLIIntegration
        except ImportError:
            pass
        
        try:
            from .codex_cli import CodexCLIIntegration
            self._integrations['codex'] = CodexCLIIntegration
        except ImportError:
            pass
        
        try:
            from .cursor_cli import CursorCLIIntegration
            self._integrations['cursor'] = CursorCLIIntegration
        except ImportError:
            pass
    
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
        
        self._integrations[name] = integration_class
    
    def unregister(self, name: str) -> bool:
        """
        Unregister an external agent integration.
        
        Args:
            name: Name of the integration to unregister
            
        Returns:
            bool: True if the integration was found and removed, False otherwise
        """
        if name in self._integrations:
            del self._integrations[name]
            return True
        return False
    
    def create(self, name: str, **kwargs: Any) -> Optional[BaseCLIIntegration]:
        """
        Create an instance of the specified integration.
        
        Args:
            name: Name of the integration
            **kwargs: Arguments to pass to the integration constructor
            
        Returns:
            BaseCLIIntegration: Instance of the integration, or None if not found
        """
        integration_class = self._integrations.get(name)
        if integration_class is None:
            return None
        
        return integration_class(**kwargs)
    
    def list_registered(self) -> List[str]:
        """
        List all registered integration names.
        
        Returns:
            List[str]: List of registered integration names
        """
        return list(self._integrations.keys())
    
    async def get_available(self) -> Dict[str, bool]:
        """
        Get availability status of all registered integrations.
        
        Returns:
            Dict[str, bool]: Mapping of integration name to availability status
        """
        availability = {}
        
        for name, integration_class in self._integrations.items():
            try:
                # Create a temporary instance to check availability
                instance = integration_class()
                availability[name] = instance.is_available
            except Exception:
                # If instantiation fails, mark as unavailable
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


# Factory functions for convenient access
def get_registry() -> ExternalAgentRegistry:
    """
    Get the singleton external agent registry.
    
    Returns:
        ExternalAgentRegistry: The singleton registry instance
    """
    return ExternalAgentRegistry.get_instance()


def register_integration(name: str, integration_class: Type[BaseCLIIntegration]) -> None:
    """
    Register a new external agent integration.
    
    Args:
        name: Unique name for the integration
        integration_class: The integration class (must inherit from BaseCLIIntegration)
    """
    registry = get_registry()
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
    registry = get_registry()
    return registry.create(name, **kwargs)


async def get_available_integrations() -> Dict[str, bool]:
    """
    Get availability status of all registered integrations.
    
    Backward compatibility wrapper for the original function.
    
    Returns:
        Dict[str, bool]: Mapping of integration name to availability status
    """
    registry = get_registry()
    return await registry.get_available()