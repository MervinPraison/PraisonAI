"""
Sandboxed Agent Backend — local agent loop with OPTIONAL tool sandboxing.

Tools are sandboxed when compute= is provided (E2B, Modal, etc.).
Without compute=, tools run locally. Agent loop always stays local.

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

# Single source of truth: aliases are defined in managed_local.py.
# This module only re-exports them as a discoverable import path.
from .managed_local import SandboxedAgent, SandboxedAgentConfig

__all__ = [
    "SandboxedAgent",
    "SandboxedAgentConfig",
]