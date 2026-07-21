"""CLI Backends for PraisonAI.

Wrapper implementations of CLI backend protocols following AGENTS.md:
- Core SDK defines protocols (praisonaiagents.cli_backend)  
- Wrapper provides concrete implementations (praisonai.cli_backends)
- Lazy loading to avoid heavy imports at startup
"""

def _is_cli_backend_instance(obj) -> bool:
    """Return True if ``obj`` is a pre-resolved CliBackendProtocol instance.

    Uses ``isinstance`` against the ``@runtime_checkable`` ``CliBackendProtocol``
    so a look-alike that merely exposes ``execute()``/``stream()`` (e.g. a
    ``BaseCLIIntegration`` coding-CLI tool, which returns ``str`` and lacks
    ``config``/``capabilities()``) is NOT mistaken for a backend. This single
    predicate is the one place the protocol shape is checked, so any future
    protocol change touches exactly one function.
    """
    try:
        from praisonaiagents.cli_backend.protocols import CliBackendProtocol
    except ImportError:
        return False
    return isinstance(obj, CliBackendProtocol)


def resolve_cli_backend_config(value):
    """Resolve a YAML/Python cli_backend value (str | dict | instance) to a CliBackendProtocol.
    
    Unified resolver that handles both YAML and Python entry points consistently.
    
    Args:
        value: CLI backend configuration - str, dict, or instance
        
    Returns:
        CliBackendProtocol instance or None
        
    Raises:
        ValueError: If configuration is invalid
    """
    if value is None:
        return None

    # Pre-resolved protocol instance: a CliBackendProtocol exposes execute() + stream().
    if _is_cli_backend_instance(value):
        return value

    # Factory callable (not itself a protocol instance) - return as-is; the core
    # Agent invokes it to obtain the protocol instance.
    if callable(value):
        return value

    # Import registry functions
    from .registry import resolve_cli_backend
    
    if isinstance(value, str):
        if not value.strip():
            raise ValueError("cli_backend string cannot be empty")
        return resolve_cli_backend(value)
    elif isinstance(value, dict):
        backend_id = value.get('id')
        if not backend_id:
            raise ValueError("cli_backend dict must contain an 'id' field")
        overrides = value.get('overrides') or {}
        if not isinstance(overrides, dict):
            raise ValueError("cli_backend.overrides must be a dict")
        return resolve_cli_backend(backend_id, overrides=overrides)
    else:
        # A look-alike that exposes execute()/stream() but is not a
        # CliBackendProtocol (e.g. a BaseCLIIntegration coding-CLI tool) reaches
        # here. Fail fast at construction with a pointed hint instead of letting
        # it crash deep in the agent loop with an opaque AttributeError.
        if hasattr(value, "execute") and hasattr(value, "stream"):
            raise TypeError(
                f"{type(value).__name__} exposes execute()/stream() but is not a "
                "CliBackendProtocol (it lacks config/capabilities() and returns a "
                "plain str). If this is a coding-CLI integration, pass it as a tool "
                "via tools=[...], not cli_backend=."
            )
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
    "_is_cli_backend_instance",
    "ClaudeCodeBackend",
    "list_cli_backends"
]