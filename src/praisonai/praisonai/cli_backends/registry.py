"""CLI Backend Registry.

Plugin registry for CLI backend implementations following AGENTS.md patterns:
- Thread-safe registration with factory pattern
- YAML override merge for declarative configuration
- Minimal dependencies (no heavy imports at module level)
"""

import threading
from typing import Dict, Callable, Any, Optional, Union
from .._registry import PluginRegistry

# CLI Backend Registry using canonical PluginRegistry
def _get_builtin_cli_backend_loaders() -> Dict[str, Callable[[], Any]]:
    """Get built-in CLI backend loaders."""
    def claude_loader():
        def factory():
            from .claude import ClaudeCodeBackend
            return ClaudeCodeBackend()
        return factory
    
    return {
        "claude-code": claude_loader
    }

# Global CLI backend registry instance
_cli_backend_registry: Optional[PluginRegistry] = None
_registry_lock = threading.Lock()

def _get_cli_backend_registry() -> PluginRegistry:
    """Get the CLI backend registry instance."""
    global _cli_backend_registry
    if _cli_backend_registry is None:
        with _registry_lock:
            if _cli_backend_registry is None:
                _cli_backend_registry = PluginRegistry(
                    entry_point_group="praisonai.cli_backends",
                    builtins=_get_builtin_cli_backend_loaders()
                )
    return _cli_backend_registry


def register_cli_backend(backend_id: str, factory: Callable[[], Any]) -> None:
    """Register a CLI backend factory.
    
    Args:
        backend_id: Unique identifier (e.g., "claude-code", "codex-cli") 
        factory: Factory function that returns a CliBackendProtocol instance
    """
    # Wrap factory in a loader function for PluginRegistry
    def factory_loader():
        return factory
    
    registry = _get_cli_backend_registry()
    registry.register(backend_id, factory_loader)


def list_cli_backends() -> list[str]:
    """List all registered CLI backend IDs."""
    registry = _get_cli_backend_registry()
    return registry.list_names()


def resolve_cli_backend(
    backend_id: str, 
    overrides: Optional[Dict[str, Any]] = None
) -> Any:
    """Resolve a CLI backend by ID with optional configuration overrides.
    
    Args:
        backend_id: Backend identifier (e.g., "claude-code")
        overrides: Optional configuration overrides to merge with defaults
        
    Returns:
        CliBackendProtocol instance
        
    Raises:
        ValueError: If backend_id is not registered
    """
    registry = _get_cli_backend_registry()
    
    try:
        # Get the factory loader and create the factory
        factory_loader = registry.resolve(backend_id)
        factory = factory_loader()
    except ValueError:
        available = registry.list_names()
        raise ValueError(f"Unknown CLI backend: {backend_id}. Available: {available}")
    
    # Create instance with factory
    backend = factory()
    
    # Apply overrides if provided
    if overrides:
        # Merge overrides into backend.config
        if not hasattr(backend, 'config'):
            raise TypeError(f"CLI backend '{backend_id}' does not expose a config object")

        unknown_keys = [key for key in overrides if not hasattr(backend.config, key)]
        if unknown_keys:
            available = sorted(vars(backend.config).keys())
            raise ValueError(
                f"Unknown override(s) for CLI backend '{backend_id}': {unknown_keys}. "
                f"Available config fields: {available}"
            )

        for key, value in overrides.items():
            setattr(backend.config, key, value)
    
    return backend


# Built-in backends are now registered via _get_builtin_cli_backend_loaders()