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
        compute="e2b",                           # or "modal", "flyio", "daytona", "docker", None
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
    - Optional compute= for cloud tool sandboxing (E2B, Modal, Docker, etc.)
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
        **kwargs,
    ):
        # Reject the provider= overload pattern to force clean usage
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
        
        # Pass compute= as the compute parameter to the underlying implementation
        super().__init__(compute=compute, config=config, **kwargs)