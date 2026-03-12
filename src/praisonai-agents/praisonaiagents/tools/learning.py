"""
Learning tools for PraisonAI agents.

Provides store_learning and search_learning as standard tool functions.
These are the Learn system counterparts to store_memory/search_memory.

Memory stores flat facts ("User's name is Alice").
Learning stores categorized knowledge ("User prefers bullet points" → persona).

Usage:
    from praisonaiagents import Agent
    from praisonaiagents.tools import store_learning, search_learning

    agent = Agent(
        instructions="You learn user preferences.",
        memory=True,
        learn=True,
        tools=[store_learning, search_learning]
    )
"""

from typing import Optional, List, Dict, Any
from .injected import Injected, AgentState, get_current_state


# Valid categories mapping to LearnManager capture methods
_CATEGORY_MAP = {
    "persona": "capture_persona",
    "insights": "capture_insight",
    "patterns": "capture_pattern",
    "decisions": "capture_decision",
    "feedback": "capture_feedback",
    "improvements": "capture_improvement",
}


def store_learning(
    content: str,
    category: str = "persona",
    state: Injected[AgentState] = None,
) -> str:
    """Store a learning — a pattern, preference, insight, or decision.

    Use this when you discover something worth remembering across sessions,
    like user preferences, behavioral patterns, or important decisions.

    Categories:
        persona — User preferences and profile (default)
        insights — Observations about the user or domain
        patterns — Recurring behaviors or workflows
        decisions — Decision records for consistency

    Args:
        content: The learning to store
        category: Category — "persona", "insights", "patterns", or "decisions"
    """
    # Resolve injected state
    if state is None:
        state = get_current_state()

    learn_mgr = getattr(state, "learn_manager", None) if state else None
    if not learn_mgr:
        return "Learning is not configured for this agent. Enable learn=True to use learning tools."

    # Normalize category
    cat = category.lower().strip()
    if cat not in _CATEGORY_MAP:
        return f"Unknown category '{category}'. Use: {', '.join(_CATEGORY_MAP.keys())}"

    method_name = _CATEGORY_MAP[cat]
    method = getattr(learn_mgr, method_name, None)
    if not method:
        return f"Learn manager does not support category '{cat}'."

    try:
        result = method(content)
        # Friendly category labels for response
        labels = {
            "persona": "persona preference",
            "insights": "insight",
            "patterns": "pattern",
            "decisions": "decision",
            "feedback": "feedback",
            "improvements": "improvement",
        }
        label = labels.get(cat, cat)
        return f"Stored {label}: {content[:100]}"
    except Exception as e:
        return f"Error storing learning: {e}"


def search_learning(
    query: str,
    category: str = "",
    limit: int = 5,
    state: Injected[AgentState] = None,
) -> str:
    """Search learned knowledge — preferences, patterns, insights, decisions.

    Use this to recall previously learned information about the user
    or domain across sessions.

    Args:
        query: What to search for
        category: Optional — filter to specific category (persona, insights, patterns, decisions)
        limit: Maximum number of results to return
    """
    # Resolve injected state
    if state is None:
        state = get_current_state()

    learn_mgr = getattr(state, "learn_manager", None) if state else None
    if not learn_mgr:
        return "Learning is not configured for this agent. Enable learn=True to use learning tools."

    try:
        all_results = learn_mgr.search(query, limit=limit)
    except Exception as e:
        return f"Error searching learnings: {e}"

    # Filter by category if specified
    if category:
        cat = category.lower().strip()
        all_results = {k: v for k, v in all_results.items() if k == cat}

    if not all_results:
        return f"No learnings found matching: {query}"

    # Format results grouped by category
    parts: List[str] = []
    total = 0
    for store_name, entries in all_results.items():
        for entry in entries[:limit]:
            text = entry.get("content", "") if isinstance(entry, dict) else str(entry)
            if text:
                parts.append(f"- [{store_name}] {text}")
                total += 1

    if not parts:
        return f"No learnings found matching: {query}"

    formatted = "\n".join(parts[:limit])
    return f"Found {min(total, limit)} learnings:\n{formatted}"
