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
    """
    
    def __init__(
        self,
        provider: str = "anthropic",
        config: Optional[Any] = None,
        **kwargs,
    ):
        if provider != "anthropic":
            # Provide differentiated guidance based on provider type
            _llm_hints = {"openai", "gemini", "ollama", "local"}
            _compute_hints = {"e2b", "modal", "flyio", "daytona", "docker"}
            
            if provider in _llm_hints:
                hint = (
                    f"For local agent loops with this LLM, use: "
                    f"LocalAgent(config=LocalAgentConfig(model='...')) "
                    f"(e.g. 'gpt-4o-mini', 'gemini/gemini-2.0-flash', 'ollama/llama3')."
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
            
            raise ValueError(
                f"Managed runtime for provider '{provider}' is not yet available. "
                f"Currently supported: 'anthropic'. {hint}"
            )
        
        # Pass through to the existing Anthropic implementation
        super().__init__(provider=provider, config=config, **kwargs)