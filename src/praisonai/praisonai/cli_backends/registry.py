"""CLI Backend Registry.

Plugin registry for CLI backend implementations following AGENTS.md patterns:
- Thread-safe registration with factory pattern
- YAML override merge for declarative configuration
- Minimal dependencies (no heavy imports at module level)
"""

import threading
from typing import Dict, Callable, Any, Optional, Union

# Thread-safe registry for CLI backend factories
_REGISTRY: Dict[str, Callable[[], Any]] = {}
_REGISTRY_LOCK = threading.Lock()


def register_cli_backend(backend_id: str, factory: Callable[[], Any]) -> None:
    """Register a CLI backend factory.
    
    Args:
        backend_id: Unique identifier (e.g., "claude-code", "codex-cli") 
        factory: Factory function that returns a CliBackendProtocol instance
    """
    with _REGISTRY_LOCK:
        _REGISTRY[backend_id] = factory


def list_cli_backends() -> list[str]:
    """List all registered CLI backend IDs."""
    with _REGISTRY_LOCK:
        return list(_REGISTRY.keys())


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
    with _REGISTRY_LOCK:
        if backend_id not in _REGISTRY:
            available = list(_REGISTRY.keys())
            raise ValueError(f"Unknown CLI backend: {backend_id}. Available: {available}")
        
        factory = _REGISTRY[backend_id]
    
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


def _register_builtin_backends() -> None:
    """Register built-in CLI backends (lazy loaded)."""
    # Only register if not already done
    with _REGISTRY_LOCK:
        if "claude-code" in _REGISTRY:
            return
    
    def claude_factory():
        from .claude import ClaudeCodeBackend
        return ClaudeCodeBackend()
    
    register_cli_backend("claude-code", claude_factory)


# Auto-register built-in backends on first access
def __getattr__(name: str):
    """Lazy registration trigger."""
    _register_builtin_backends()
    raise AttributeError(f"No attribute {name}")

# Trigger registration on import
_register_builtin_backends()