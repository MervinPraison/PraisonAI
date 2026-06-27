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

from typing import AsyncIterator, Optional, Any
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
    """
    
    def __init__(
        self,
        provider: str = "anthropic",
        config: Optional[Any] = None,
        **kwargs,
    ):
        # Consult the managed-backend registry so entry-point plugins can add
        # providers without editing this file. "anthropic" is the only builtin.
        from .backend_registry import get_backend_registry

        registry = get_backend_registry()
        if not registry.is_available(provider):
            raise ValueError(self._unavailable_provider_message(provider))

        # Anthropic — and any backend that is a subclass of this class' own
        # base (AnthropicManagedAgent) — is initialised in-place via
        # ``super().__init__`` so all inherited methods operate on fully
        # initialised state. Because ``HostedAgent`` IS-A ``AnthropicManagedAgent``
        # and subclasses share its constructor contract, this keeps the
        # Anthropic-compatible path fully functional.
        backend_cls = registry.resolve(provider)
        if issubclass(backend_cls, AnthropicManagedAgent):
            super().__init__(provider=provider, config=config, **kwargs)
        else:  # pragma: no cover - exercised once non-anthropic backends exist
            # A foreign backend (not an AnthropicManagedAgent) cannot share our
            # inherited execute()/stream()/session methods, so we fully delegate
            # to it. Inherited attribute access is forwarded via __getattr__
            # below, ensuring no method ever runs against uninitialised state.
            self._delegate = backend_cls(provider=provider, config=config, **kwargs)
            self.provider = provider

    # --- ManagedBackendProtocol forwarding ----------------------------------
    # When HostedAgent delegates to a foreign backend, the methods it INHERITS
    # from AnthropicManagedAgent would otherwise shadow the delegate and run
    # against uninitialised state (no super().__init__ ran). These thin
    # overrides forward the protocol surface to the delegate when present, and
    # fall through to the inherited Anthropic implementation otherwise.

    async def execute(self, prompt: str, **kwargs) -> str:
        delegate = self.__dict__.get("_delegate")
        if delegate is not None:
            return await delegate.execute(prompt, **kwargs)
        return await super().execute(prompt, **kwargs)

    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        delegate = self.__dict__.get("_delegate")
        if delegate is not None:
            async for chunk in delegate.stream(prompt, **kwargs):
                yield chunk
            return
        async for chunk in super().stream(prompt, **kwargs):
            yield chunk

    def reset_session(self) -> None:
        delegate = self.__dict__.get("_delegate")
        if delegate is not None:
            return delegate.reset_session()
        return super().reset_session()

    def reset_all(self) -> None:
        delegate = self.__dict__.get("_delegate")
        if delegate is not None:
            return delegate.reset_all()
        return super().reset_all()

    def __getattr__(self, item: str) -> Any:
        # Only reached for attributes NOT found on the instance/class. When a
        # foreign backend was delegated to, forward any remaining attribute
        # access to it so HostedAgent acts as a transparent proxy rather than
        # exposing uninitialised inherited state.
        if item == "_delegate":
            raise AttributeError(item)
        delegate = self.__dict__.get("_delegate")
        if delegate is not None:
            return getattr(delegate, item)
        raise AttributeError(item)

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