"""
Turn-time runtime resolution API for handoffs and sub-agents.

This module addresses the issue where handoffs and sub-agents inherit
construction-time runtime pins from the parent agent, causing wrong
harness execution when the delegate uses a different model_ref or provider.

The solution provides turn-time resolution that re-resolves runtime
from (agent_id, model_ref) at each handoff/sub-agent invocation.
"""

import logging
import threading
import time
from typing import Any, Dict, Optional, Protocol, Tuple, Union
from dataclasses import dataclass
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class RuntimeProtocol(Protocol):
    """Protocol for agent runtime implementations."""
    
    def execute(self, prompt: str, **kwargs) -> Any:
        """Execute a prompt with the runtime."""
        ...
    
    async def aexecute(self, prompt: str, **kwargs) -> Any:
        """Async execute a prompt with the runtime."""
        ...
    
    @property
    def model_ref(self) -> str:
        """Get the model reference for this runtime."""
        ...
    
    @property
    def provider(self) -> str:
        """Get the provider for this runtime."""
        ...

class AgentRuntimeProtocol(RuntimeProtocol):
    """Extended protocol for agent-specific runtime features."""
    
    @property
    def supports_streaming(self) -> bool:
        """Whether this runtime supports streaming responses."""
        ...
    
    @property
    def supports_tools(self) -> bool:
        """Whether this runtime supports tool calling."""
        ...

@dataclass
class SessionContext:
    """Context for runtime resolution within a session."""
    session_id: str
    timestamp: float
    parent_agent_id: Optional[str] = None
    handoff_depth: int = 0
    
    def __post_init__(self):
        if self.timestamp <= 0:
            self.timestamp = time.time()

class RuntimeResolver(ABC):
    """Abstract base class for runtime resolution strategies."""
    
    @abstractmethod
    def resolve(
        self, 
        agent_id: str, 
        model_ref: str, 
        session_ctx: SessionContext,
        **kwargs
    ) -> AgentRuntimeProtocol:
        """Resolve runtime for the given agent and model."""
        ...
    
    @abstractmethod
    def supports_model(self, model_ref: str) -> bool:
        """Check if this resolver can handle the given model."""
        ...

class DefaultRuntimeResolver(RuntimeResolver):
    """Default runtime resolver that creates appropriate runtime instances."""
    
    def __init__(self):
        self._model_mapping = {
            # OpenAI models
            'gpt-4o': 'openai',
            'gpt-4o-mini': 'openai', 
            'gpt-4': 'openai',
            'gpt-3.5-turbo': 'openai',
            # Anthropic models
            'claude-3-sonnet': 'anthropic',
            'claude-3-haiku': 'anthropic',
            'claude-3-opus': 'anthropic',
            # Add more mappings as needed
        }
    
    def supports_model(self, model_ref: str) -> bool:
        """Check if we can resolve this model."""
        return model_ref in self._model_mapping or model_ref.startswith(('gpt-', 'claude-'))
    
    def resolve(
        self, 
        agent_id: str, 
        model_ref: str, 
        session_ctx: SessionContext,
        **kwargs
    ) -> AgentRuntimeProtocol:
        """Resolve runtime based on model reference."""
        try:
            # Try to import and use the existing LLM class
            from ..llm.llm import LLM
            
            # Create a runtime wrapper around the LLM
            # Pass through any configuration kwargs
            llm_kwargs = {'model': model_ref}
            llm_kwargs.update(kwargs)
            return LLMRuntimeWrapper(
                llm=LLM(**llm_kwargs),
                model_ref=model_ref,
                agent_id=agent_id
            )
        except ImportError:
            # Fallback to a basic implementation
            logger.warning(f"LLM class not available, using fallback runtime for {model_ref}")
            return FallbackRuntime(model_ref=model_ref, agent_id=agent_id)

class LLMRuntimeWrapper(AgentRuntimeProtocol):
    """Wrapper around existing LLM class to provide runtime protocol."""
    
    def __init__(self, llm: Any, model_ref: str, agent_id: str):
        self.llm = llm
        self._model_ref = model_ref
        self._agent_id = agent_id
    
    def execute(self, prompt: str, **kwargs) -> Any:
        """Execute prompt using the LLM."""
        return self.llm.chat(prompt, **kwargs)
    
    async def aexecute(self, prompt: str, **kwargs) -> Any:
        """Async execute prompt using the LLM."""
        if hasattr(self.llm, 'achat'):
            return await self.llm.achat(prompt, **kwargs)
        else:
            # Run sync version in executor
            import asyncio
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: self.llm.chat(prompt, **kwargs))
    
    @property
    def model_ref(self) -> str:
        return self._model_ref
    
    @property
    def provider(self) -> str:
        # Extract provider from model_ref or LLM instance
        if hasattr(self.llm, 'provider'):
            return self.llm.provider
        elif self._model_ref.startswith('gpt-'):
            return 'openai'
        elif self._model_ref.startswith('claude-'):
            return 'anthropic'
        else:
            return 'unknown'
    
    @property
    def supports_streaming(self) -> bool:
        return hasattr(self.llm, 'stream') or hasattr(self.llm, '_stream_chat')
    
    @property
    def supports_tools(self) -> bool:
        return True  # Most modern LLMs support tools

class FallbackRuntime(AgentRuntimeProtocol):
    """Fallback runtime implementation that raises errors instead of returning stubs."""
    
    def __init__(self, model_ref: str, agent_id: str):
        self._model_ref = model_ref
        self._agent_id = agent_id
    
    def execute(self, prompt: str, **kwargs) -> Any:
        raise RuntimeError(
            f"No LLM runtime available for model {self._model_ref}. "
            "Please ensure the LLM module is properly installed."
        )
    
    async def aexecute(self, prompt: str, **kwargs) -> Any:
        raise RuntimeError(
            f"No LLM runtime available for model {self._model_ref}. "
            "Please ensure the LLM module is properly installed."
        )
    
    @property
    def model_ref(self) -> str:
        return self._model_ref
    
    @property
    def provider(self) -> str:
        return 'fallback'
    
    @property
    def supports_streaming(self) -> bool:
        return False
    
    @property
    def supports_tools(self) -> bool:
        return False

# Global runtime cache - thread-safe and request-scoped
_runtime_cache_lock = threading.RLock()
_runtime_cache: Dict[str, Dict[str, Tuple[AgentRuntimeProtocol, float]]] = {}
_cache_ttl_seconds = 300  # 5 minutes
_global_resolver: Optional[RuntimeResolver] = None

def set_global_resolver(resolver: RuntimeResolver) -> None:
    """Set the global runtime resolver."""
    global _global_resolver
    _global_resolver = resolver

def get_global_resolver() -> RuntimeResolver:
    """Get the global runtime resolver, creating default if needed."""
    global _global_resolver
    if _global_resolver is None:
        _global_resolver = DefaultRuntimeResolver()
    return _global_resolver

def resolve_runtime(
    agent_id: str, 
    model_ref: str, 
    session_ctx: SessionContext,
    **kwargs
) -> AgentRuntimeProtocol:
    """
    Resolve runtime for the given agent and model at turn-time.
    
    This is the main API that handoffs and sub-agent invocations should call
    to get the appropriate runtime instead of using construction-time pins.
    
    Args:
        agent_id: Unique identifier for the agent
        model_ref: Model reference (e.g., 'gpt-4o', 'claude-3-sonnet')  
        session_ctx: Session context for caching and tracking
        
    Returns:
        AgentRuntimeProtocol instance configured for the model
        
    Raises:
        RuntimeError: If no suitable runtime can be resolved
        
    Example:
        ```python
        session_ctx = SessionContext(
            session_id="session_123",
            timestamp=time.time(),
            handoff_depth=1
        )
        runtime = resolve_runtime("agent_1", "gpt-4o", session_ctx)
        response = runtime.execute("Hello, world!")
        ```
    """
    cache_key = f"{session_ctx.session_id}:{agent_id}:{model_ref}"
    current_time = time.time()
    
    # Check cache first
    with _runtime_cache_lock:
        session_cache = _runtime_cache.get(session_ctx.session_id, {})
        
        if cache_key in session_cache:
            runtime, cached_time = session_cache[cache_key]
            # Check if cache entry is still valid
            if current_time - cached_time < _cache_ttl_seconds:
                logger.debug(f"Using cached runtime for {cache_key}")
                return runtime
            else:
                # Remove expired entry
                del session_cache[cache_key]
                logger.debug(f"Cache expired for {cache_key}")
    
    # Resolve new runtime
    logger.info(f"Resolving runtime for agent_id={agent_id}, model_ref={model_ref}")
    
    resolver = get_global_resolver()
    if not resolver.supports_model(model_ref):
        raise RuntimeError(f"No runtime resolver available for model: {model_ref}")
    
    try:
        runtime = resolver.resolve(agent_id, model_ref, session_ctx, **kwargs)
        
        # Cache the resolved runtime
        with _runtime_cache_lock:
            if session_ctx.session_id not in _runtime_cache:
                _runtime_cache[session_ctx.session_id] = {}
            _runtime_cache[session_ctx.session_id][cache_key] = (runtime, current_time)
            
        logger.info(f"Successfully resolved runtime for {cache_key}")
        return runtime
        
    except Exception as e:
        logger.error(f"Failed to resolve runtime for {cache_key}: {e}")
        raise RuntimeError(f"Runtime resolution failed for model {model_ref}: {e}") from e

def get_runtime_cache() -> Dict[str, Dict[str, Tuple[AgentRuntimeProtocol, float]]]:
    """Get a copy of the current runtime cache (for debugging/testing)."""
    with _runtime_cache_lock:
        return {
            session_id: {
                key: (runtime, timestamp) 
                for key, (runtime, timestamp) in cache.items()
            }
            for session_id, cache in _runtime_cache.items()
        }

def clear_runtime_cache(session_id: Optional[str] = None) -> None:
    """
    Clear runtime cache for a specific session or all sessions.
    
    Args:
        session_id: If provided, only clear cache for this session.
                   If None, clear all cached runtimes.
    """
    with _runtime_cache_lock:
        if session_id is None:
            _runtime_cache.clear()
            logger.info("Cleared all runtime cache")
        elif session_id in _runtime_cache:
            del _runtime_cache[session_id]
            logger.info(f"Cleared runtime cache for session: {session_id}")

def _cleanup_expired_cache() -> None:
    """Clean up expired cache entries (called periodically)."""
    current_time = time.time()
    total_expired = 0
    
    with _runtime_cache_lock:
        for session_id, session_cache in list(_runtime_cache.items()):
            expired_keys = []
            for key, (runtime, cached_time) in session_cache.items():
                if current_time - cached_time >= _cache_ttl_seconds:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del session_cache[key]
            total_expired += len(expired_keys)
            
            # Remove empty session caches
            if not session_cache:
                del _runtime_cache[session_id]
    
    if total_expired:
        logger.debug(f"Cleaned up {total_expired} expired runtime cache entries")

# Background cleanup (optional - only if needed)
_cleanup_thread = None
_cleanup_interval = 600  # 10 minutes

def _start_cleanup_thread():
    """Start background cache cleanup thread."""
    global _cleanup_thread
    if _cleanup_thread is None or not _cleanup_thread.is_alive():
        def cleanup_worker():
            while True:
                try:
                    time.sleep(_cleanup_interval)
                    _cleanup_expired_cache()
                except Exception as e:
                    logger.error(f"Cache cleanup error: {e}")
        
        _cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        _cleanup_thread.start()
        logger.debug("Started runtime cache cleanup thread")

# Initialize cleanup thread when module is imported
_start_cleanup_thread()