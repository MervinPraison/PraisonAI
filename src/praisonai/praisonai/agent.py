"""Wrapper Agent class with CLI backend resolution support.

This module provides a wrapper around praisonaiagents.Agent that handles
CLI backend string resolution in the wrapper layer, maintaining proper
dependency direction per AGENTS.md.
"""

from typing import Union, Optional, Any
from praisonaiagents import Agent as CoreAgent


class Agent(CoreAgent):
    """Agent wrapper with CLI backend string resolution support.
    
    This class extends the core Agent to handle CLI backend string resolution
    in the wrapper layer, maintaining proper architectural separation between
    core protocols and heavy implementations.
    """
    
    def __init__(self, *args, cli_backend: Optional[Union[str, Any]] = None, **kwargs):
        """Initialize Agent with CLI backend string resolution.
        
        Args:
            *args: Positional arguments for core Agent
            cli_backend: CLI backend for delegating full turns. Accepts:
                - str: Backend ID ("claude-code", "codex-cli") - resolved in wrapper
                - CliBackendProtocol: Pre-resolved backend instance
                - callable: Factory function returning CliBackendProtocol
                - None: No CLI backend
            **kwargs: Keyword arguments for core Agent
        """
        # Resolve string CLI backends to instances in wrapper layer
        if isinstance(cli_backend, str):
            cli_backend = self._resolve_string_backend(cli_backend)
        
        # Pass resolved backend to core Agent
        super().__init__(*args, cli_backend=cli_backend, **kwargs)
    
    def _resolve_string_backend(self, backend_id: str) -> Any:
        """Resolve string backend ID to CliBackendProtocol instance.
        
        Args:
            backend_id: Backend identifier (e.g., "claude-code")
            
        Returns:
            CliBackendProtocol instance
            
        Raises:
            ImportError: If CLI backends module not available
            ValueError: If backend_id is not registered
        """
        try:
            from .cli_backends import resolve_cli_backend
            return resolve_cli_backend(backend_id)
        except ImportError:
            raise ImportError(
                f"CLI backend '{backend_id}' requested but CLI backends not available. "
                "This may indicate a packaging or installation issue."
            )


# Export the wrapper Agent as the default for import from praisonai
__all__ = ["Agent"]