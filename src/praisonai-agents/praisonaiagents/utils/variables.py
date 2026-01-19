"""
Dynamic Variable Providers for PraisonAI Workflows.

Provides protocol-driven dynamic variable substitution for {{variable}} placeholders
that resolve at runtime rather than requiring static values.

Built-in providers:
- now: Current datetime (ISO format)
- today: Current date (human-readable)
- date: Current date (YYYY-MM-DD)
- uuid: Random UUID
- timestamp: Unix timestamp

Usage in YAML:
    variables:
      current_date: "{{today}}"
      topic: "Latest AI news for {{today}}"

Usage in Python:
    from praisonaiagents.workflows.variable_providers import get_provider_registry
    
    registry = get_provider_registry()
    registry.register("custom", MyCustomProvider())
"""

import threading
import uuid as uuid_module
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Any, Callable, Dict, Optional, Union


class DynamicVariableProvider(ABC):
    """
    Protocol for dynamic variable providers.
    
    Implement this class to create custom dynamic variables
    that resolve at runtime.
    
    Example:
        class CounterProvider(DynamicVariableProvider):
            def __init__(self):
                self._count = 0
            
            def get_value(self) -> int:
                self._count += 1
                return self._count
    """
    
    @abstractmethod
    def get_value(self) -> Any:
        """Get the current value of this dynamic variable."""
        ...


# =============================================================================
# Built-in Providers
# =============================================================================

class NowProvider(DynamicVariableProvider):
    """Returns current datetime in ISO format."""
    
    def get_value(self) -> str:
        return datetime.now().isoformat()


class TodayProvider(DynamicVariableProvider):
    """Returns current date in human-readable format (e.g., 'January 19, 2026')."""
    
    def get_value(self) -> str:
        return date.today().strftime("%B %d, %Y")


class DateProvider(DynamicVariableProvider):
    """Returns current date in YYYY-MM-DD format."""
    
    def get_value(self) -> str:
        return date.today().strftime("%Y-%m-%d")


class TimestampProvider(DynamicVariableProvider):
    """Returns current Unix timestamp."""
    
    def get_value(self) -> int:
        return int(datetime.now().timestamp())


class UUIDProvider(DynamicVariableProvider):
    """Returns a new random UUID."""
    
    def get_value(self) -> str:
        return str(uuid_module.uuid4())


class YearProvider(DynamicVariableProvider):
    """Returns current year."""
    
    def get_value(self) -> int:
        return date.today().year


class MonthProvider(DynamicVariableProvider):
    """Returns current month name."""
    
    def get_value(self) -> str:
        return date.today().strftime("%B")


# =============================================================================
# Provider Registry
# =============================================================================

class VariableProviderRegistry:
    """
    Central registry for dynamic variable providers.
    
    Thread-safe for multi-agent scenarios.
    
    Usage:
        registry = get_provider_registry()
        value = registry.resolve("today")  # "January 19, 2026"
    """
    
    def __init__(self):
        self._providers: Dict[str, DynamicVariableProvider] = {}
        self._functions: Dict[str, Callable[[], Any]] = {}
        self._lock = threading.RLock()
        self._register_builtins()
    
    def _register_builtins(self) -> None:
        """Register built-in providers."""
        self._providers["now"] = NowProvider()
        self._providers["today"] = TodayProvider()
        self._providers["date"] = DateProvider()
        self._providers["timestamp"] = TimestampProvider()
        self._providers["uuid"] = UUIDProvider()
        self._providers["year"] = YearProvider()
        self._providers["month"] = MonthProvider()
    
    def register(
        self,
        name: str,
        provider: Union[DynamicVariableProvider, Callable[[], Any]],
        overwrite: bool = False
    ) -> None:
        """
        Register a dynamic variable provider.
        
        Args:
            name: Variable name (used as {{name}})
            provider: DynamicVariableProvider instance or callable
            overwrite: If True, overwrite existing provider
        
        Raises:
            ValueError: If provider exists and overwrite=False
        """
        with self._lock:
            if name in self._providers or name in self._functions:
                if not overwrite:
                    raise ValueError(f"Provider '{name}' already registered")
            
            if isinstance(provider, DynamicVariableProvider):
                self._providers[name] = provider
            elif callable(provider):
                self._functions[name] = provider
            else:
                raise TypeError(f"Expected DynamicVariableProvider or callable, got {type(provider)}")
    
    def unregister(self, name: str) -> bool:
        """Remove a provider."""
        with self._lock:
            if name in self._providers:
                del self._providers[name]
                return True
            if name in self._functions:
                del self._functions[name]
                return True
            return False
    
    def resolve(self, name: str) -> Optional[Any]:
        """
        Resolve a dynamic variable by name.
        
        Args:
            name: Variable name
            
        Returns:
            Resolved value, or None if not found
        """
        with self._lock:
            if name in self._providers:
                return self._providers[name].get_value()
            if name in self._functions:
                return self._functions[name]()
            return None
    
    def has(self, name: str) -> bool:
        """Check if a provider exists."""
        with self._lock:
            return name in self._providers or name in self._functions
    
    def list_providers(self) -> list:
        """List all registered provider names."""
        with self._lock:
            return list(self._providers.keys()) + list(self._functions.keys())
    
    def __contains__(self, name: str) -> bool:
        return self.has(name)


# =============================================================================
# Global Registry
# =============================================================================

_global_registry: Optional[VariableProviderRegistry] = None


def get_provider_registry() -> VariableProviderRegistry:
    """Get the global variable provider registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = VariableProviderRegistry()
    return _global_registry


def register_variable_provider(
    name: str,
    provider: Union[DynamicVariableProvider, Callable[[], Any]]
) -> None:
    """Convenience function to register a provider with the global registry."""
    get_provider_registry().register(name, provider)


def resolve_dynamic_variable(name: str) -> Optional[Any]:
    """Convenience function to resolve a dynamic variable."""
    return get_provider_registry().resolve(name)


# =============================================================================
# Shared Variable Substitution Utility (DRY)
# =============================================================================

def substitute_variables(text: str, variables: Dict[str, Any]) -> str:
    """
    Substitute {{variable}} placeholders in text.
    
    This is the canonical, DRY implementation used by all workflow modules.
    
    Resolution order:
    1. Dynamic variable providers ({{now}}, {{today}}, {{uuid}}, etc.)
    2. Static variables from the provided variables dict
    3. Keep original placeholder if not found
    
    Args:
        text: Text containing {{variable}} placeholders
        variables: Static variables dict
        
    Returns:
        Text with variables substituted
        
    Example:
        >>> substitute_variables("Hello {{today}} - {{name}}", {"name": "World"})
        "Hello January 19, 2026 - World"
    """
    import re
    
    provider_registry = get_provider_registry()
    
    def replace(match):
        var_name = match.group(1).strip()
        
        # First check dynamic providers
        if provider_registry.has(var_name):
            return str(provider_registry.resolve(var_name))
        
        # Then check static variables
        if var_name in variables:
            return str(variables[var_name])
        
        # Keep original if not found
        return match.group(0)
    
    return re.sub(r'\{\{(\w+)\}\}', replace, text)
