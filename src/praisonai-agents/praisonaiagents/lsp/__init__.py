"""
LSP Integration Module for PraisonAI Agents.

Provides Language Server Protocol integration for code intelligence:
- Diagnostics (errors, warnings)
- Code completion suggestions
- Go to definition
- Find references
- Hover information

Zero Performance Impact:
- All imports are lazy loaded via __getattr__
- LSP client only initialized when needed
- No overhead when not in use

Usage:
    from praisonaiagents.lsp import LSPClient
    
    # Create client for a language
    client = LSPClient(language="python")
    
    # Start the language server
    await client.start()
    
    # Get diagnostics for a file
    diagnostics = await client.get_diagnostics("/path/to/file.py")
    
    # Get completions at a position
    completions = await client.get_completions("/path/to/file.py", line=10, character=5)
"""

__all__ = [
    # Core client
    "LSPClient",
    # Data types
    "Diagnostic",
    "DiagnosticSeverity",
    "CompletionItem",
    "Location",
    "Position",
    "Range",
    # Configuration
    "LSPConfig",
]


def __getattr__(name: str):
    """Lazy load module components to avoid import overhead."""
    if name == "LSPClient":
        from .client import LSPClient
        return LSPClient
    
    if name in ("Diagnostic", "DiagnosticSeverity", "CompletionItem", 
                "Location", "Position", "Range"):
        from .types import (
            Diagnostic, DiagnosticSeverity, CompletionItem,
            Location, Position, Range
        )
        return locals()[name]
    
    if name == "LSPConfig":
        from .config import LSPConfig
        return LSPConfig
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
