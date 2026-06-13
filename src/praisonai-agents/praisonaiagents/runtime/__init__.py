"""Runtime system for PraisonAI agents.

This module provides the runtime abstraction layer that allows agents to execute
through different runtime implementations (built-in embedded loop, CLI backends, etc.).

Protocol-driven design following AGENTS.md:
- Lightweight protocols only (no heavy implementations)
- Async-first with proper typing
- Plugin registry for runtime extensions
"""

from .protocols import AgentRuntimeProtocol, RuntimeConfig, RuntimeResult, RuntimeDelta
from .registry import RuntimeRegistry, register_runtime, list_runtimes, resolve_runtime

__all__ = [
    'AgentRuntimeProtocol',
    'RuntimeConfig', 
    'RuntimeResult',
    'RuntimeDelta',
    'RuntimeRegistry',
    'register_runtime',
    'list_runtimes', 
    'resolve_runtime',
]