"""
Sandboxed Agent Backend — local agent loop with remote tool execution.

Renamed from "LocalManagedAgent" to accurately communicate that only TOOLS
run in sandbox — the agent loop (LLM calls, event handling, memory) stays local.

For true managed runtime where the ENTIRE LOOP runs remotely, see:
- AnthropicManagedAgent (Anthropic-hosted)
- E2BManagedAgent (E2B-hosted) 
- ModalManagedAgent (Modal-hosted)

Implements ``ManagedBackendProtocol`` from the Core SDK.

Usage::

    from praisonai.integrations.sandboxed_agent import SandboxedAgent, SandboxedAgentConfig
    from praisonaiagents import Agent

    sandboxed = SandboxedAgent(
        compute="e2b",  # Tools run in E2B, loop stays local
        config=SandboxedAgentConfig(
            model="gpt-4o",
            system="You are a coding assistant.",
        )
    )
    agent = Agent(name="coder", backend=sandboxed)
    result = agent.start("Create a Python script that prints hello")
"""

# Import entire implementation from managed_local and re-export with new names
from .managed_local import (
    LocalManagedAgent as SandboxedAgent,
    LocalManagedConfig as SandboxedAgentConfig,
    _translate_anthropic_tools,
    _build_custom_tool_fn,
    _DEFAULT_SYSTEM,
    _DEFAULT_TOOLS,
)

# Re-export for import consistency
__all__ = [
    "SandboxedAgent", 
    "SandboxedAgentConfig",
    "_translate_anthropic_tools",
    "_build_custom_tool_fn", 
    "_DEFAULT_SYSTEM",
    "_DEFAULT_TOOLS",
]