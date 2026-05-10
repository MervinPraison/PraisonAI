"""CLI Backends for PraisonAI.

Wrapper implementations of CLI backend protocols following AGENTS.md:
- Core SDK defines protocols (praisonaiagents.cli_backend)  
- Wrapper provides concrete implementations (praisonai.cli_backends)
- Lazy loading to avoid heavy imports at startup
"""

def resolve_cli_backend_config(value, logger=None):
    """Resolve a YAML/Python cli_backend value (str | dict | instance) to a CliBackendProtocol.
    
    Unified resolver that handles both YAML and Python entry points consistently.
    
    Args:
        value: CLI backend configuration - str, dict, or instance
        logger: Optional logger for warnings
        
    Returns:
        CliBackendProtocol instance or None
        
    Raises:
        ValueError: If configuration is invalid
    """
    if not value:
        return None
        
    # If already an instance, return as-is (duck typing)
    if hasattr(value, '__call__') or hasattr(value, 'process_turn'):
        return value
        
    # Import registry functions
    from .registry import resolve_cli_backend
    
    if isinstance(value, str):
        return resolve_cli_backend(value)
    elif isinstance(value, dict):
        backend_id = value.get('id')
        if not backend_id:
            raise ValueError("cli_backend dict must contain an 'id' field")
        overrides = value.get('overrides', {})
        return resolve_cli_backend(backend_id, overrides=overrides)
    else:
        raise ValueError(
            f"cli_backend must be string, dict, or instance, got: {type(value).__name__}"
        )

def __getattr__(name: str):
    """Lazy loading for CLI backend implementations."""
    if name == "register_cli_backend":
        from .registry import register_cli_backend
        return register_cli_backend
    elif name == "resolve_cli_backend":
        from .registry import resolve_cli_backend
        return resolve_cli_backend
    elif name == "ClaudeCodeBackend":
        from .claude import ClaudeCodeBackend
        return ClaudeCodeBackend
    elif name == "list_cli_backends":
        from .registry import list_cli_backends
        return list_cli_backends
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

__all__ = [
    "register_cli_backend",
    "resolve_cli_backend", 
    "resolve_cli_backend_config",
    "ClaudeCodeBackend",
    "list_cli_backends"
]