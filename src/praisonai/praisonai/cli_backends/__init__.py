"""CLI Backends for PraisonAI.

Wrapper implementations of CLI backend protocols following AGENTS.md:
- Core SDK defines protocols (praisonaiagents.cli_backend)  
- Wrapper provides concrete implementations (praisonai.cli_backends)
- Lazy loading to avoid heavy imports at startup
"""

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
    "ClaudeCodeBackend",
    "list_cli_backends"
]