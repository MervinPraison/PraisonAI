"""
Dynamic Context Discovery for PraisonAI.

This module provides filesystem-backed implementations for:
- Artifact storage (tool outputs, history, terminal logs)
- Tool output queuing middleware
- History persistence with search
- Terminal session logging

Zero Performance Impact:
- All imports are lazy loaded
- Features only activate when explicitly enabled
- No overhead when not used

Usage:
    from praisonai.context import (
        FileSystemArtifactStore,
        OutputQueue,
        HistoryStore,
        TerminalLogger,
    )
    
    # Create artifact store
    store = FileSystemArtifactStore(base_dir="~/.praison/runs")
    
    # Create output queue
    queue = OutputQueue(store=store, inline_max_kb=32)
"""

__all__ = [
    # Artifact Store
    "FileSystemArtifactStore",
    # Output Queue
    "OutputQueue",
    "create_queue_middleware",
    "create_artifact_tools",
    # History
    "HistoryStore",
    "create_history_tools",
    "create_history_pointer",
    # Terminal
    "TerminalLogger",
    "create_terminal_tools",
    # Config
    "DynamicContextConfig",
    # Setup
    "DynamicContextSetup",
    "setup_dynamic_context",
]


def __getattr__(name: str):
    """Lazy load module components."""
    if name == "FileSystemArtifactStore":
        from .artifact_store import FileSystemArtifactStore
        return FileSystemArtifactStore
    
    # New user-friendly names
    if name == "OutputQueue":
        from .queue import OutputQueue
        return OutputQueue
    
    if name == "create_queue_middleware":
        from .queue import create_queue_middleware
        return create_queue_middleware
    
    
    if name == "create_artifact_tools":
        from .queue import create_artifact_tools
        return create_artifact_tools
    
    if name == "HistoryStore":
        from .history_store import HistoryStore
        return HistoryStore
    
    if name == "create_history_tools":
        from .history_store import create_history_tools
        return create_history_tools
    
    if name == "create_history_pointer":
        from .history_store import create_history_pointer
        return create_history_pointer
    
    if name == "TerminalLogger":
        from .terminal_logger import TerminalLogger
        return TerminalLogger
    
    if name == "create_terminal_tools":
        from .terminal_logger import create_terminal_tools
        return create_terminal_tools
    
    if name == "DynamicContextConfig":
        from .config import DynamicContextConfig
        return DynamicContextConfig
    
    if name == "DynamicContextSetup":
        from .setup import DynamicContextSetup
        return DynamicContextSetup
    
    if name == "setup_dynamic_context":
        from .setup import setup_dynamic_context
        return setup_dynamic_context
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
