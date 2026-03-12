"""
Memory tools for PraisonAI agents.

Provides store_memory and search_memory as standard tool functions.
Agents use them via tools=[store_memory, search_memory] — like any other tool.

Memory access is provided through the Injected[AgentState] mechanism,
which is hidden from the LLM's tool schema.

Usage:
    from praisonaiagents import Agent
    from praisonaiagents.tools import store_memory, search_memory

    agent = Agent(
        instructions="You remember important facts.",
        memory=True,
        tools=[store_memory, search_memory]
    )
"""

from typing import Optional, List, Dict, Any
from .injected import Injected, AgentState, get_current_state


def store_memory(
    content: str,
    memory_type: str = "long_term",
    state: Injected[AgentState] = None,
) -> str:
    """Store important information for later recall.

    Use this when the user tells you something worth remembering,
    like preferences, facts, or important context.

    Args:
        content: The information to remember
        memory_type: Type of memory — "short_term" for temporary, "long_term" for persistent
    """
    # Resolve injected state
    if state is None:
        state = get_current_state()

    memory = getattr(state, "memory", None) if state else None
    if not memory:
        return "Memory is not configured for this agent. Enable memory=True to use memory tools."

    try:
        if memory_type == "short_term":
            if hasattr(memory, "store_short_term"):
                memory.store_short_term(content)
            elif hasattr(memory, "add_short_term"):
                memory.add_short_term(content)
            else:
                return "Memory backend does not support short-term storage."
        else:
            # Default to long_term
            if hasattr(memory, "store_long_term"):
                memory.store_long_term(content)
            elif hasattr(memory, "add_long_term"):
                memory.add_long_term(content)
            else:
                return "Memory backend does not support long-term storage."

        return f"Stored in {memory_type} memory: {content[:100]}"
    except Exception as e:
        return f"Error storing memory: {e}"


def search_memory(
    query: str,
    limit: int = 5,
    state: Injected[AgentState] = None,
) -> str:
    """Search your memory for relevant information.

    Use this when you need to recall something the user
    previously told you or that you previously stored.

    Args:
        query: What to search for
        limit: Maximum number of results to return
    """
    # Resolve injected state
    if state is None:
        state = get_current_state()

    memory = getattr(state, "memory", None) if state else None
    if not memory:
        return "Memory is not configured for this agent. Enable memory=True to use memory tools."

    results: List[str] = []

    try:
        # Search long-term memory first (most important)
        if hasattr(memory, "search_long_term"):
            lt_results = memory.search_long_term(query, limit=limit)
            if lt_results:
                for item in lt_results:
                    text = _extract_text(item)
                    if text:
                        results.append(text)

        # Also check short-term memory
        if hasattr(memory, "search_short_term"):
            st_results = memory.search_short_term(query, limit=limit)
            if st_results:
                for item in st_results:
                    text = _extract_text(item)
                    if text and text not in results:
                        results.append(text)

        # Fallback: try generic search method
        if not results and hasattr(memory, "search"):
            generic_results = memory.search(query, limit=limit)
            if generic_results:
                for item in generic_results:
                    text = _extract_text(item)
                    if text:
                        results.append(text)

    except Exception as e:
        return f"Error searching memory: {e}"

    if not results:
        return f"No memories found matching: {query}"

    # Format results
    formatted = "\n".join(f"- {r}" for r in results[:limit])
    return f"Found {len(results[:limit])} memories:\n{formatted}"


def _extract_text(item: Any) -> Optional[str]:
    """Extract text content from a memory search result."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return item.get("text") or item.get("content") or item.get("memory") or str(item)
    if hasattr(item, "content"):
        return item.content
    if hasattr(item, "text"):
        return item.text
    return str(item) if item else None
