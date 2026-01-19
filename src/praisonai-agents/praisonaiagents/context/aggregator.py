"""
Context Aggregator for PraisonAI Agents.

Aggregates context from multiple memory sources concurrently.
Inspired by CrewAI's ContextualMemory pattern.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


@dataclass
class AggregatedContext:
    """Result of context aggregation."""
    context: str = ""
    sources_used: List[str] = field(default_factory=list)
    tokens_used: int = 0
    fetch_times: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "context": self.context[:500] + "..." if len(self.context) > 500 else self.context,
            "sources_used": self.sources_used,
            "tokens_used": self.tokens_used,
            "fetch_times": self.fetch_times,
        }


class ContextAggregator:
    """
    Aggregates context from multiple memory sources concurrently.
    
    Implements the CrewAI ContextualMemory pattern for PraisonAI.
    Fetches from memory, knowledge, and RAG in parallel and merges results.
    
    Example:
        aggregator = ContextAggregator()
        
        # Register sources
        aggregator.register_source("memory", memory.search)
        aggregator.register_source("knowledge", knowledge.search)
        aggregator.register_source("rag", rag.retrieve)
        
        # Aggregate context
        result = await aggregator.aggregate("user query", max_tokens=4000)
        print(result.context)
    """
    
    def __init__(
        self,
        max_tokens: int = 4000,
        separator: str = "\n\n---\n\n",
        include_source_labels: bool = True,
    ):
        """
        Initialize context aggregator.
        
        Args:
            max_tokens: Maximum tokens for aggregated context
            separator: Separator between source contexts
            include_source_labels: Whether to label each source section
        """
        self.max_tokens = max_tokens
        self.separator = separator
        self.include_source_labels = include_source_labels
        
        # Registered context sources: name -> (fetch_fn, priority)
        self._sources: Dict[str, Tuple[Callable, int]] = {}
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (4 chars per token heuristic)."""
        return len(text) // 4 + 1
    
    def register_source(
        self,
        name: str,
        fetch_fn: Callable[[str], Union[str, List[Dict[str, Any]]]],
        priority: int = 50,
    ) -> None:
        """
        Register a context source.
        
        Args:
            name: Source name (e.g., "memory", "knowledge", "rag")
            fetch_fn: Function that takes query and returns context
            priority: Priority (lower = first, 0-100)
        """
        self._sources[name] = (fetch_fn, priority)
    
    def unregister_source(self, name: str) -> None:
        """Remove a registered source."""
        self._sources.pop(name, None)
    
    @property
    def sources(self) -> List[str]:
        """Get list of registered source names."""
        return list(self._sources.keys())
    
    async def _fetch_source(
        self,
        name: str,
        query: str,
    ) -> Tuple[str, Optional[str], float]:
        """
        Fetch context from a single source.
        
        Returns: (context_str, source_name, fetch_time)
        """
        import time
        
        fetch_fn, _ = self._sources.get(name, (None, 0))
        if not fetch_fn:
            return "", None, 0.0
        
        start = time.time()
        try:
            # Call the fetch function
            if asyncio.iscoroutinefunction(fetch_fn):
                result = await fetch_fn(query)
            else:
                # Run sync function in executor
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, fetch_fn, query)
            
            # Convert result to string
            if isinstance(result, str):
                context = result
            elif isinstance(result, list):
                # Handle list of results (e.g., from memory search)
                parts = []
                for item in result:
                    if isinstance(item, dict):
                        text = item.get("text") or item.get("memory") or item.get("content", "")
                        if text:
                            parts.append(str(text))
                    elif isinstance(item, str):
                        parts.append(item)
                context = "\n".join(parts)
            else:
                context = str(result) if result else ""
            
            elapsed = time.time() - start
            return context, name, elapsed
            
        except Exception as e:
            logger.warning(f"Failed to fetch from {name}: {e}")
            return "", None, time.time() - start
    
    async def aggregate(
        self,
        query: str,
        sources: Optional[List[str]] = None,
        max_tokens: Optional[int] = None,
    ) -> AggregatedContext:
        """
        Aggregate context from multiple sources concurrently.
        
        Args:
            query: Search query
            sources: Specific sources to use (default: all registered)
            max_tokens: Override max tokens
            
        Returns:
            AggregatedContext with merged results
        """
        max_tokens = max_tokens or self.max_tokens
        sources_to_use = sources or list(self._sources.keys())
        
        if not sources_to_use:
            return AggregatedContext()
        
        # Filter to registered sources only
        sources_to_use = [s for s in sources_to_use if s in self._sources]
        
        if not sources_to_use:
            return AggregatedContext()
        
        # Fetch from all sources concurrently
        tasks = [
            self._fetch_source(name, query)
            for name in sources_to_use
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        contexts: List[Tuple[str, str, float, int]] = []  # (context, name, time, priority)
        fetch_times: Dict[str, float] = {}
        
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Source fetch failed: {result}")
                continue
            
            context, name, elapsed = result
            if context and name:
                _, priority = self._sources.get(name, (None, 50))
                contexts.append((context, name, elapsed, priority))
                fetch_times[name] = elapsed
        
        # Sort by priority (lower = first)
        contexts.sort(key=lambda x: x[3])
        
        # Merge and truncate to fit token budget
        merged_parts = []
        total_tokens = 0
        sources_used = []
        separator_tokens = self._estimate_tokens(self.separator)
        
        for context, name, _, _ in contexts:
            context_tokens = self._estimate_tokens(context)
            
            # Check if we can fit this context
            if total_tokens + context_tokens + separator_tokens > max_tokens:
                # Try to fit partial
                remaining = max_tokens - total_tokens - separator_tokens
                if remaining > 100:
                    # Truncate context
                    chars_to_keep = int(remaining * 4 * 0.9)
                    truncated = context[:chars_to_keep] + "..."
                    
                    if self.include_source_labels:
                        merged_parts.append(f"**{name}**:\n{truncated}")
                    else:
                        merged_parts.append(truncated)
                    
                    sources_used.append(name)
                    total_tokens += self._estimate_tokens(truncated)
                break
            
            if self.include_source_labels:
                merged_parts.append(f"**{name}**:\n{context}")
            else:
                merged_parts.append(context)
            
            sources_used.append(name)
            total_tokens += context_tokens + separator_tokens
        
        merged_context = self.separator.join(merged_parts)
        
        return AggregatedContext(
            context=merged_context,
            sources_used=sources_used,
            tokens_used=total_tokens,
            fetch_times=fetch_times,
        )
    
    def aggregate_sync(
        self,
        query: str,
        sources: Optional[List[str]] = None,
        max_tokens: Optional[int] = None,
    ) -> AggregatedContext:
        """
        Synchronous version of aggregate.
        
        Args:
            query: Search query
            sources: Specific sources to use
            max_tokens: Override max tokens
            
        Returns:
            AggregatedContext with merged results
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create a new loop for sync execution
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self.aggregate(query, sources, max_tokens)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.aggregate(query, sources, max_tokens)
                )
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(self.aggregate(query, sources, max_tokens))


def create_aggregator_from_config(
    memory = None,
    knowledge = None,
    rag = None,
    max_tokens: int = 4000,
) -> ContextAggregator:
    """
    Create a ContextAggregator with standard sources.
    
    Args:
        memory: Memory instance with search() method
        knowledge: Knowledge instance with search() method
        rag: RAG instance with retrieve() method
        max_tokens: Maximum tokens for aggregated context
        
    Returns:
        Configured ContextAggregator
    """
    aggregator = ContextAggregator(max_tokens=max_tokens)
    
    if memory and hasattr(memory, 'search_short_term'):
        aggregator.register_source("memory", memory.search_short_term, priority=10)
    
    if knowledge and hasattr(knowledge, 'search'):
        aggregator.register_source("knowledge", knowledge.search, priority=20)
    
    if rag and hasattr(rag, 'retrieve'):
        aggregator.register_source("rag", rag.retrieve, priority=30)
    
    return aggregator
