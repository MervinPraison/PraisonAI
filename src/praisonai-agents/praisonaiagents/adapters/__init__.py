"""
Adapter Layer for Core SDK.

Provides a clean interface between core protocols and implementations.
This layer reduces tight coupling between wrapper and core by offering:
- Single entry point for wrapper → core interaction
- Protocol-based interfaces instead of direct imports
- Backward compatibility while enabling architectural improvements

Usage:
    ```python
    from praisonaiagents.adapters import CoreAdapter, AgentConfig
    
    # Instead of importing core internals directly
    adapter = CoreAdapter()
    config = AgentConfig(name="assistant", instructions="Be helpful")
    agent = adapter.create_agent(config)
    memory = adapter.create_memory(MemoryConfig(provider="chroma"))
    ```
"""

from .core_adapter import (
    CoreAdapter, 
    AgentConfig, 
    MemoryConfig, 
    LLMConfig,
    create_agent,
    create_memory
)

__all__ = [
    'CoreAdapter',
    'AgentConfig', 
    'MemoryConfig', 
    'LLMConfig',
    'create_agent',
    'create_memory'
]