"""Wrapper Agent class with CLI backend resolution support.

This module provides a wrapper around praisonaiagents.Agent that handles
CLI backend string resolution in the wrapper layer, maintaining proper
dependency direction per AGENTS.md.
"""

from typing import Union, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:  # zero runtime cost — only for static analysis / IDEs
    from praisonaiagents import Agent as CoreAgent


def _build_agent_class():
    """Construct the wrapper Agent class, importing the heavy core lazily.

    ``praisonaiagents`` (and its transitive ``asyncio``/``ssl`` cost) is only
    imported here, on first construction of the class, keeping
    ``from praisonai import Agent`` cheap until the class is actually used.
    """
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
                    - dict: Backend config {"id": "claude-code", "overrides": {...}}
                    - CliBackendProtocol: Pre-resolved backend instance
                    - callable: Factory function returning CliBackendProtocol
                    - None: No CLI backend
                **kwargs: Keyword arguments for core Agent
            """
            # Deprecation warning will be emitted by the core Agent class
            # Resolve CLI backend configuration using unified resolver
            if cli_backend is not None and not self._is_protocol_instance(cli_backend):
                from .cli_backends import resolve_cli_backend_config
                cli_backend = resolve_cli_backend_config(cli_backend)

            # Pass resolved backend to core Agent
            super().__init__(*args, cli_backend=cli_backend, **kwargs)

        def _is_protocol_instance(self, obj) -> bool:
            """Check if object is a pre-resolved CliBackendProtocol instance (duck typing).

            A CliBackendProtocol instance exposes both ``execute()`` and ``stream()``.
            Factory callables are intentionally NOT treated as protocol instances here
            so that wrapper-level normalization in ``resolve_cli_backend_config`` runs.
            """
            return hasattr(obj, "execute") and hasattr(obj, "stream")

    return Agent


_Agent = None


def __getattr__(name: str):
    """Lazily build and cache the wrapper ``Agent`` class on first access.

    This defers the eager ``praisonaiagents`` import (previously at module top)
    so that reaching ``praisonai.agent`` no longer pays ~420 ms up front. The
    class is built and cached on first attribute access.
    """
    global _Agent
    if name == "Agent":
        if _Agent is None:
            _Agent = _build_agent_class()
        return _Agent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Export the wrapper Agent as the default for import from praisonai
__all__ = ["Agent"]