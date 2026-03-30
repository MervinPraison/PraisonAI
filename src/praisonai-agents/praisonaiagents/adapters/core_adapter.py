"""
Core Adapter - Single Entry Point for Wrapper → Core Interaction.

This adapter provides a clean, protocol-driven interface between the wrapper layer
and core SDK, reducing the 657+ direct imports from core internals.

Design Goals:
- Reduce tight coupling between wrapper and core
- Provide stable API that doesn't break when core internals change
- Enable protocol-based testing and mocking
- Maintain backward compatibility during architectural transitions
"""
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from ..agent.agent import Agent
    from ..memory.protocols import MemoryProtocol, AgentMemoryProtocol
    from ..llm.protocols import LLMProtocol
    from ..storage.protocols import StorageBackendProtocol


@dataclass
class AgentConfig:
    """Configuration for creating agents via adapter."""
    name: str
    instructions: Optional[str] = None
    llm: Optional[str] = None
    tools: Optional[List[Any]] = None
    memory: Union[bool, Dict[str, Any], None] = None
    kwargs: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.kwargs is None:
            self.kwargs = {}


@dataclass  
class MemoryConfig:
    """Configuration for creating memory instances via adapter."""
    provider: str = "file"  # file, chroma, mem0, mongodb, etc.
    auto_save: Optional[str] = None
    use_long_term: bool = False
    kwargs: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.kwargs is None:
            self.kwargs = {}


@dataclass
class LLMConfig:
    """Configuration for creating LLM instances via adapter."""
    model: str
    provider: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    kwargs: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.kwargs is None:
            self.kwargs = {}


class CoreAdapter:
    """
    Single entry point for wrapper → core interaction.
    
    This adapter encapsulates core SDK creation patterns and provides a stable
    interface that won't break when core internals are refactored.
    
    Example:
        ```python
        # Wrapper code using adapter (stable)
        from praisonaiagents.adapters import CoreAdapter
        
        adapter = CoreAdapter()
        
        # Create components via adapter instead of direct imports
        agent = adapter.create_agent(AgentConfig(
            name="assistant", 
            instructions="Be helpful"
        ))
        
        memory = adapter.create_memory(MemoryConfig(
            provider="chroma", 
            use_long_term=True
        ))
        
        # Instead of 657+ direct imports like:
        # from praisonaiagents.agent.agent import Agent  # ❌ tight coupling
        ```
    """
    
    def __init__(self):
        """Initialize adapter with lazy imports to avoid startup penalties."""
        self._agent_class = None
        self._memory_classes = {}
        self._llm_classes = {}
    
    def create_agent(self, config: AgentConfig) -> "Agent":
        """
        Create an Agent instance using protocol-driven configuration.
        
        Args:
            config: Agent configuration object
            
        Returns:
            Configured Agent instance
            
        Example:
            ```python
            config = AgentConfig(
                name="researcher",
                instructions="Research topics thoroughly",
                llm="gpt-4o-mini",
                memory=True
            )
            agent = adapter.create_agent(config)
            ```
        """
        # Lazy import to avoid startup penalty
        if self._agent_class is None:
            from ..agent.agent import Agent
            self._agent_class = Agent
        
        # Convert config to Agent constructor arguments
        kwargs = {
            'name': config.name,
            **config.kwargs
        }
        
        if config.instructions:
            kwargs['instructions'] = config.instructions
        if config.llm:
            kwargs['llm'] = config.llm
        if config.tools:
            kwargs['tools'] = config.tools
        if config.memory is not None:
            kwargs['memory'] = config.memory
            
        return self._agent_class(**kwargs)
    
    def create_memory(self, config: MemoryConfig) -> "MemoryProtocol":
        """
        Create a memory instance using protocol-driven configuration.
        
        Args:
            config: Memory configuration object
            
        Returns:
            Memory instance implementing MemoryProtocol
            
        Example:
            ```python
            config = MemoryConfig(
                provider="chroma", 
                use_long_term=True,
                auto_save="my_session"
            )
            memory = adapter.create_memory(config)
            ```
        """
        # Lazy import based on provider
        if config.provider not in self._memory_classes:
            if config.provider == "file":
                from ..memory.file_memory import FileMemory
                self._memory_classes[config.provider] = FileMemory
            elif config.provider in ("chroma", "memory", "default"):
                from ..memory.memory import Memory
                self._memory_classes[config.provider] = Memory
            else:
                raise ValueError(f"Unknown memory provider: {config.provider}")
        
        memory_class = self._memory_classes[config.provider]
        
        # Convert config to memory constructor arguments
        kwargs = config.kwargs.copy()
        if config.auto_save:
            kwargs['auto_save'] = config.auto_save
        if config.use_long_term:
            kwargs['use_long_term'] = config.use_long_term
            
        return memory_class(**kwargs)
    
    def create_llm(self, config: LLMConfig) -> "LLMProtocol":
        """
        Create an LLM instance using protocol-driven configuration.
        
        Args:
            config: LLM configuration object
            
        Returns:
            LLM instance implementing LLMProtocol
            
        Example:
            ```python
            config = LLMConfig(
                model="gpt-4o-mini",
                temperature=0.7,
                max_tokens=1000
            )
            llm = adapter.create_llm(config)
            ```
        """
        # For now, delegate to existing LLM class
        # In future phases, this will create protocol-based LLM instances
        provider = config.provider or "openai"
        
        if provider not in self._llm_classes:
            from ..llm.llm import LLM
            self._llm_classes[provider] = LLM
        
        llm_class = self._llm_classes[provider]
        
        # Convert config to LLM constructor arguments
        kwargs = config.kwargs.copy()
        kwargs['model'] = config.model
        if config.temperature is not None:
            kwargs['temperature'] = config.temperature
        if config.max_tokens is not None:
            kwargs['max_tokens'] = config.max_tokens
            
        return llm_class(**kwargs)
    
    def create_storage(self, backend_type: str = "json", **kwargs) -> "StorageBackendProtocol":
        """
        Create a storage backend using protocol-driven configuration.
        
        Args:
            backend_type: Type of storage backend (json, sqlite, etc.)
            **kwargs: Backend-specific configuration
            
        Returns:
            Storage backend implementing StorageBackendProtocol
        """
        if backend_type == "json":
            from ..storage.backends import JSONBackend
            return JSONBackend(**kwargs)
        elif backend_type == "sqlite":
            from ..storage.backends import SQLiteBackend
            return SQLiteBackend(**kwargs)
        else:
            raise ValueError(f"Unknown storage backend: {backend_type}")
    
    def get_protocols(self) -> Dict[str, type]:
        """
        Get available protocol interfaces.
        
        Returns:
            Dictionary mapping protocol names to protocol classes
            
        Example:
            ```python
            protocols = adapter.get_protocols()
            memory_protocol = protocols['MemoryProtocol']
            llm_protocol = protocols['LLMProtocol']
            ```
        """
        from ..memory.protocols import MemoryProtocol, AgentMemoryProtocol
        from ..llm.protocols import LLMProtocol, AsyncLLMProtocol
        from ..storage.protocols import StorageBackendProtocol
        
        return {
            'MemoryProtocol': MemoryProtocol,
            'AgentMemoryProtocol': AgentMemoryProtocol,
            'LLMProtocol': LLMProtocol,
            'AsyncLLMProtocol': AsyncLLMProtocol,
            'StorageBackendProtocol': StorageBackendProtocol,
        }


# Convenience factory functions for common use cases
def create_agent(name: str, **kwargs) -> "Agent":
    """
    Quick agent creation without explicit config.
    
    Example:
        ```python
        from praisonaiagents.adapters import create_agent
        
        agent = create_agent("assistant", instructions="Be helpful")
        ```
    """
    adapter = CoreAdapter()
    config = AgentConfig(name=name, **kwargs)
    return adapter.create_agent(config)


def create_memory(provider: str = "file", **kwargs) -> "MemoryProtocol":
    """
    Quick memory creation without explicit config.
    
    Example:
        ```python
        from praisonaiagents.adapters import create_memory
        
        memory = create_memory("chroma", use_long_term=True)
        ```
    """
    adapter = CoreAdapter()
    config = MemoryConfig(provider=provider, **kwargs)
    return adapter.create_memory(config)