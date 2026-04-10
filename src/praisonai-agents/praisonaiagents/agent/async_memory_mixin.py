"""
Async memory operations mixin for the Agent class.

Provides async-safe memory operations that can be used in async contexts
without blocking the event loop. This extends the base MemoryMixin with
async capabilities following the AsyncMemoryProtocol.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Union
from praisonaiagents._logging import get_logger
from ..memory.protocols import AsyncMemoryProtocol

logger = get_logger(__name__)


class AsyncMemoryMixin:
    """
    Mixin providing async-safe memory operations for agents.
    
    This mixin adds async memory methods that can be used in async contexts
    like async agent execution methods (achat, arun, astart) without
    blocking the event loop.
    """
    
    async def astore_memory(
        self,
        content: str, 
        memory_type: str = "short_term",
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Optional[str]:
        """
        Async store content in agent memory.
        
        Args:
            content: Content to store
            memory_type: "short_term" or "long_term"
            metadata: Optional metadata
            **kwargs: Additional parameters
            
        Returns:
            Memory ID if successful, None otherwise
        """
        if not hasattr(self, '_memory_instance') or self._memory_instance is None:
            logger.debug("No memory configured for async storage")
            return None
            
        # Check if memory adapter supports async operations
        if isinstance(self._memory_instance, AsyncMemoryProtocol):
            try:
                if memory_type == "long_term":
                    return await self._memory_instance.astore_long_term(content, metadata, **kwargs)
                else:
                    return await self._memory_instance.astore_short_term(content, metadata, **kwargs)
            except Exception as e:
                logger.error(f"Error in async memory storage: {e}")
                return None
        else:
            # Fallback: run sync memory operations in thread pool
            return await self._run_memory_in_thread(
                "store", content, memory_type, metadata, **kwargs
            )
    
    async def asearch_memory(
        self,
        query: str,
        memory_type: str = "short_term", 
        limit: int = 5,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Async search agent memory.
        
        Args:
            query: Search query
            memory_type: "short_term" or "long_term"
            limit: Maximum results
            **kwargs: Additional parameters
            
        Returns:
            List of memory entries
        """
        if not hasattr(self, '_memory_instance') or self._memory_instance is None:
            logger.debug("No memory configured for async search")
            return []
            
        # Check if memory adapter supports async operations
        if isinstance(self._memory_instance, AsyncMemoryProtocol):
            try:
                if memory_type == "long_term":
                    return await self._memory_instance.asearch_long_term(query, limit, **kwargs)
                else:
                    return await self._memory_instance.asearch_short_term(query, limit, **kwargs)
            except Exception as e:
                logger.error(f"Error in async memory search: {e}")
                return []
        else:
            # Fallback: run sync memory operations in thread pool
            return await self._run_memory_in_thread(
                "search", query, memory_type, limit=limit, **kwargs
            )
    
    async def _run_memory_in_thread(
        self,
        operation: str,
        content: str,
        memory_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        limit: int = 5,
        **kwargs
    ) -> Union[str, List[Dict[str, Any]], None]:
        """
        Run synchronous memory operations in a thread pool to avoid blocking.
        
        Args:
            operation: "store" or "search"
            content: Content to store or query to search
            memory_type: "short_term" or "long_term"
            metadata: Optional metadata for store operations
            limit: Limit for search operations
            **kwargs: Additional parameters
            
        Returns:
            Result of the memory operation
        """
        loop = asyncio.get_running_loop()
        
        try:
            if operation == "store":
                if memory_type == "long_term" and hasattr(self._memory_instance, 'store_long_term'):
                    return await loop.run_in_executor(
                        None, 
                        lambda: self._memory_instance.store_long_term(content, metadata, **kwargs)
                    )
                elif hasattr(self._memory_instance, 'store_short_term'):
                    return await loop.run_in_executor(
                        None,
                        lambda: self._memory_instance.store_short_term(content, metadata, **kwargs)
                    )
            elif operation == "search":
                if memory_type == "long_term" and hasattr(self._memory_instance, 'search_long_term'):
                    return await loop.run_in_executor(
                        None,
                        lambda: self._memory_instance.search_long_term(content, limit, **kwargs)
                    )
                elif hasattr(self._memory_instance, 'search_short_term'):
                    return await loop.run_in_executor(
                        None,
                        lambda: self._memory_instance.search_short_term(content, limit, **kwargs)
                    )
                    
        except Exception as e:
            logger.error(f"Error in threaded memory operation {operation}: {e}")
            
        return [] if operation == "search" else None
    
    async def _async_build_memory_context(
        self,
        query: str,
        max_memories: int = 10,
        memory_types: List[str] = None
    ) -> str:
        """
        Async version of _build_memory_context that doesn't block the event loop.
        
        Args:
            query: Query to search for relevant memories
            max_memories: Maximum number of memories to include
            memory_types: Types of memory to search ("short_term", "long_term")
            
        Returns:
            Formatted memory context string
        """
        if memory_types is None:
            memory_types = ["short_term", "long_term"]
            
        all_memories = []
        
        # Search each memory type asynchronously
        for memory_type in memory_types:
            memories = await self.asearch_memory(
                query, 
                memory_type=memory_type,
                limit=max_memories // len(memory_types)
            )
            all_memories.extend(memories)
            
        # Sort by relevance/recency and limit total
        all_memories = all_memories[:max_memories]
        
        if not all_memories:
            return ""
            
        # Build context string
        context_lines = ["Relevant memories:"]
        for i, memory in enumerate(all_memories, 1):
            text = memory.get('text', str(memory))
            context_lines.append(f"{i}. {text}")
            
        return "\n".join(context_lines)
    
    def _ensure_async_memory_compatibility(self):
        """
        Ensure memory adapter is compatible with async operations.
        
        Logs warnings if memory adapter doesn't support async operations
        and will fall back to thread pool execution.
        """
        if hasattr(self, '_memory_instance') and self._memory_instance is not None:
            if not isinstance(self._memory_instance, AsyncMemoryProtocol):
                logger.info(
                    f"Memory adapter {type(self._memory_instance).__name__} doesn't implement "
                    f"AsyncMemoryProtocol, falling back to thread pool execution"
                )
                return False
            return True
        return False