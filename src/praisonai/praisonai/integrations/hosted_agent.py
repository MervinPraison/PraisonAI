"""
Hosted Agent — canonical name for cloud-based agent runtime backends.

This is the new canonical implementation that replaces the overloaded 
`ManagedAgent(provider="anthropic")` pattern. Currently aliases AnthropicManagedAgent
but provides a clear semantic distinction: the entire agent loop runs on a remote
managed runtime (Anthropic's cloud infrastructure).

Implements ``ManagedBackendProtocol`` from the Core SDK.

Usage::

    from praisonai.integrations import HostedAgent, HostedAgentConfig
    from praisonaiagents import Agent

    # Hosted loop — entire agent runs on Anthropic's managed runtime
    agent = Agent(name="a", backend=HostedAgent(
        provider="anthropic",
        config=HostedAgentConfig(
            model="claude-3-5-sonnet-latest",
            system="You are a concise assistant.",
        ),
    ))

Architecture: 
    - Runtime provider axis: anthropic (only supported today), e2b, modal, flyio (future)
    - Agent loop runs entirely in the cloud provider's managed runtime
    - Tools are co-located with the provider infrastructure

Provider -> backend resolution is delegated to the ``ManagedBackendRegistry``
(see :mod:`backend_registry`), so a third-party package can register a
``praisonai.managed_backends`` entry point and make ``HostedAgent(provider=...)``
work without editing this file.
"""

from typing import Optional, Any
from .managed_agents import AnthropicManagedAgent, ManagedConfig


# Use the existing ManagedConfig as HostedAgentConfig for now
# This preserves all current functionality while providing the new semantic naming
HostedAgentConfig = ManagedConfig


class HostedAgent(AnthropicManagedAgent):
    """Canonical hosted agent backend for cloud-based managed runtimes.
    
    Currently supports only Anthropic's managed runtime, but designed to extend
    cleanly to other providers (E2B-Managed, Modal-Managed, etc.) in the future.
    
    Key semantic distinction: the **entire agent loop** runs on the provider's 
    cloud infrastructure, including tools, context, and execution environment.
    
    Args:
        provider: Runtime provider name. Currently only "anthropic" is supported.
                 Future: "e2b", "modal", "flyio" when those runtimes are available.
        config: HostedAgentConfig with model, system prompt, tools, etc.
        **kwargs: Additional arguments passed to the underlying provider implementation.
    
    Raises:
        ValueError: If the specified provider is not available as a managed runtime.

    Note:
        For non-Anthropic providers registered via the
        ``praisonai.managed_backends`` entry point, ``HostedAgent(provider=...)``
        acts as a **factory**: it returns the resolved backend instance directly
        (via ``__new__``) rather than an ``AnthropicManagedAgent`` subclass
        instance. This guarantees the foreign backend's own methods are used and
        no ``AnthropicManagedAgent``-inherited member can run against
        uninitialised Anthropic state.
    """

    def __new__(
        cls,
        provider: str = "anthropic",
        config: Optional[Any] = None,
        **kwargs,
    ):
        # Consult the managed-backend registry so entry-point plugins can add
        # providers without editing this file. "anthropic" is the only builtin.
        from .backend_registry import get_backend_registry

        registry = get_backend_registry()
        if not registry.is_available(provider):
            raise ValueError(cls._unavailable_provider_message(provider))

        backend_cls = registry.resolve(provider)

        # Anthropic — and any AnthropicManagedAgent subclass — shares this
        # class' constructor contract, so we build a HostedAgent instance and
        # let __init__ run super().__init__ in-place. All inherited methods then
        # operate on fully initialised state.
        if issubclass(backend_cls, AnthropicManagedAgent):
            return super().__new__(cls)

        # A foreign backend cannot share AnthropicManagedAgent's inherited
        # execute()/stream()/session surface. Returning its instance DIRECTLY
        # (Python skips __init__ when __new__ returns a non-cls instance) makes
        # HostedAgent a true factory: callers get the real backend, so no
        # inherited member can ever shadow it or read uninitialised state.
        return backend_cls(provider=provider, config=config, **kwargs)

    def __init__(
        self,
        provider: str = "anthropic",
        config: Optional[Any] = None,
        **kwargs,
    ):
        # Only runs for the Anthropic path: __new__ returns a foreign backend
        # instance (not a HostedAgent) for other providers, so Python skips
        # __init__ entirely in that case.
        super().__init__(provider=provider, config=config, **kwargs)

    @staticmethod
    def _unavailable_provider_message(provider: str) -> str:
        """Build the actionable error message for an unsupported provider."""
        from .backend_registry import get_backend_registry

        _llm_hints = {"openai", "gemini", "ollama", "local"}
        _compute_hints = {"e2b", "modal", "flyio", "daytona", "docker"}

        if provider in _llm_hints:
            hint = (
                "For local agent loops with this LLM, use: "
                "LocalAgent(config=LocalAgentConfig(model='...')) "
                "(e.g. 'gpt-4o-mini', 'gemini/gemini-2.0-flash', 'ollama/llama3')."
            )
        elif provider in _compute_hints:
            hint = (
                f"For local execution with cloud compute, use: "
                f"LocalAgent(compute='{provider}', config=LocalAgentConfig(...))"
            )
        else:
            hint = (
                "Use LocalAgent(config=LocalAgentConfig(model='...')) for local loops, "
                "or LocalAgent(compute='e2b'|'modal'|'docker'|...) for cloud-sandboxed tools."
            )

        available = sorted(get_backend_registry().list_all_names())
        return (
            f"Managed runtime for provider '{provider}' is not yet available. "
            f"Currently supported: {available}. {hint}"
        )