"""
Sandboxed Agent Backend — provider-agnostic agent with sandboxed tool execution.

Agent loop runs locally, but tool execution is bridged to secure compute providers
(E2B, Modal, Docker, etc.). This provides the safety of remote sandboxes while
maintaining local control over the LLM loop.

Implements ``ManagedBackendProtocol`` from the Core SDK.

Usage::

    from praisonai.integrations.sandboxed_agent import SandboxedAgent, SandboxedAgentConfig
    from praisonaiagents import Agent

    sandboxed = SandboxedAgent(
        config=SandboxedAgentConfig(
            model="gpt-4o",
            system="You are a coding assistant.",
            compute="e2b",  # Tools run in E2B sandbox
        )
    )
    agent = Agent(name="coder", backend=sandboxed)
    result = agent.start("Create a Python script that prints hello")
"""

# Import everything from managed_local.py to maintain full compatibility
# This is a clean way to rename without breaking existing code
from .managed_local import *

# Re-export the main classes with new names
from .managed_local import LocalManagedAgent as SandboxedAgent
from .managed_local import LocalManagedConfig as SandboxedAgentConfig

# Keep all other exports for full backward compatibility
__all__ = [
    # New primary names
    "SandboxedAgent",
    "SandboxedAgentConfig",
    
    # Import everything else from managed_local for compatibility
] + [name for name in dir() if not name.startswith('_') and name not in ['SandboxedAgent', 'SandboxedAgentConfig']]