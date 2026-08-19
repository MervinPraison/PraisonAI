"""
Local Agent — canonical name for local agent loop with optional cloud compute.

This is the new canonical implementation that replaces the overloaded 
`ManagedAgent(provider="openai"/"gemini"/...)` pattern. The agent loop runs 
locally but can optionally use cloud compute providers for tool sandboxing.

Implements ``ManagedBackendProtocol`` from the Core SDK.

Usage::

    from praisonai.integrations import LocalAgent, LocalAgentConfig
    from praisonaiagents import Agent

    # Local loop, tools optional-sandboxed in cloud compute
    agent = Agent(name="b", backend=LocalAgent(
        tools_run_on="e2b",                      # or "modal", "flyio", "daytona", "docker", None
        config=LocalAgentConfig(
            model="gpt-4o-mini",                 # LLM choice here — not provider=
            system="You are a concise assistant.",
        ),
    ))

    # Smallest footprint: local loop + local subprocess
    agent = Agent(name="c", backend=LocalAgent(
        config=LocalAgentConfig(model="gpt-4o-mini"),
    ))

Architecture:
    - Agent loop runs locally in the current process
    - LLM selection via model= (supports litellm routing like "gemini/...", "ollama/...")
    - Optional tools_run_on= for cloud tool sandboxing (E2B, Modal, Docker, etc.)
    - No provider= overload — clean separation of concerns
"""

import warnings
from typing import Optional, Any
from .managed_local import LocalManagedAgent, LocalManagedConfig


# Use the existing LocalManagedConfig as LocalAgentConfig for now
# This preserves all current functionality while providing the new semantic naming
LocalAgentConfig = LocalManagedConfig


class LocalAgent(LocalManagedAgent):
    """Canonical local agent backend with optional cloud compute.
    
    Key semantic distinction: the **agent loop runs locally** in your process.
    Only tools can optionally be executed in a cloud compute environment for sandboxing.
    
    Args:
        compute: Optional compute provider for tool sandboxing. 
                Can be "e2b", "modal", "flyio", "daytona", "docker", or None (local subprocess).
        config: LocalAgentConfig with model, system prompt, tools, etc.
        **kwargs: Additional arguments passed to the underlying local implementation.
    
    Note:
        The legacy provider= parameter is not supported on LocalAgent constructors.
        Use config.model= for LLM selection (e.g., "gpt-4o", "gemini/gemini-2.0-flash", "ollama/llama3").
    """
    
    def __init__(
        self,
        compute: Optional[Any] = None,
        config: Optional[Any] = None,
        tools_run_on: Optional[Any] = None,
        **kwargs,
    ):
        # `compute=` and `tools_run_on=` name the same thing: where this agent's
        # shell/file tools run. `tools_run_on=` is the spelling used by Agent,
        # AgentFlow and AgentTeam, so one word now covers every class. Kept as a
        # FutureWarning rather than removed because `compute=` is the shipped
        # public name here -- and FutureWarning, not DeprecationWarning, because
        # PEP 565 hides the latter from the end users who actually wrote this
        # call (see praisonaiagents/utils/deprecation.py for the same choice).
        if compute is not None and tools_run_on is not None:
            raise TypeError(
                f"LocalAgent(compute={compute!r}, tools_run_on={tools_run_on!r}) "
                f"names the same thing twice -- where this agent's tools run. "
                f"Pass tools_run_on= only."
            )
        if compute is not None:
            warnings.warn(
                f"LocalAgent(compute={compute!r}) is now "
                f"LocalAgent(tools_run_on={compute!r}). Same behaviour, and the "
                f"same word Agent, AgentFlow and AgentTeam already use for "
                f"'where the tools run'. compute= keeps working for now.",
                FutureWarning,
                stacklevel=2,
            )
        elif tools_run_on is not None:
            compute = tools_run_on
        # Reject the provider= overload pattern to force clean usage
        provider_for_routing = "local"  # Default provider for model routing
        if 'provider' in kwargs:
            provider_value = kwargs.pop('provider')
            warnings.warn(
                f"LocalAgent() does not accept provider='{provider_value}'. "
                f"Use config.model= for LLM selection instead. "
                f"For example: LocalAgentConfig(model='gpt-4o-mini') or "
                f"LocalAgentConfig(model='gemini/gemini-2.0-flash')",
                DeprecationWarning,
                stacklevel=2
            )
            # Preserve the provider value for LLM routing to maintain backward compatibility
            # This ensures _resolve_model() can still apply proper prefixes (ollama/, gemini/, etc.)
            provider_for_routing = provider_value
        
        # Pass compute= as the compute parameter and provider for LLM routing
        super().__init__(compute=compute, config=config, provider=provider_for_routing, **kwargs)