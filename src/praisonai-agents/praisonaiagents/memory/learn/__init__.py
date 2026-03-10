"""
Learn Module - Continuous Learning within Memory System.

Provides learning capabilities for agents to capture patterns, preferences,
and insights from interactions to improve future responses.

Usage:
    from praisonaiagents import Agent, LearnConfig
    
    # Simple enable (top-level param)
    agent = Agent(learn=True)
    
    # With specific capabilities and auto-learning
    agent = Agent(learn=LearnConfig(
        persona=True,
        insights=True,
        patterns=True,
        mode="agentic",  # Auto-extract learnings
    ))
    
    # With database backend
    agent = Agent(learn=LearnConfig(
        backend="sqlite",
        db_url="sqlite:///learn.db",
    ))
"""

__all__ = [
    # Manager
    "LearnManager",
    # Stores
    "PersonaStore",
    "InsightStore",
    "ThreadStore",
    "PatternStore",
    "DecisionStore",
    "FeedbackStore",
    "ImprovementStore",
    # Protocols
    "LearnMode",
    "LearnProtocol",
    "AsyncLearnProtocol",
    "LearnManagerProtocol",
]


def __getattr__(name: str):
    """Lazy loading for learn module components."""
    # Manager
    if name == "LearnManager":
        from .manager import LearnManager
        return LearnManager
    
    # Stores
    if name == "PersonaStore":
        from .stores import PersonaStore
        return PersonaStore
    if name == "InsightStore":
        from .stores import InsightStore
        return InsightStore
    if name == "ThreadStore":
        from .stores import ThreadStore
        return ThreadStore
    if name == "PatternStore":
        from .stores import PatternStore
        return PatternStore
    if name == "DecisionStore":
        from .stores import DecisionStore
        return DecisionStore
    if name == "FeedbackStore":
        from .stores import FeedbackStore
        return FeedbackStore
    if name == "ImprovementStore":
        from .stores import ImprovementStore
        return ImprovementStore
    
    # Protocols
    if name == "LearnMode":
        from .protocols import LearnMode
        return LearnMode
    if name == "LearnProtocol":
        from .protocols import LearnProtocol
        return LearnProtocol
    if name == "AsyncLearnProtocol":
        from .protocols import AsyncLearnProtocol
        return AsyncLearnProtocol
    if name == "LearnManagerProtocol":
        from .protocols import LearnManagerProtocol
        return LearnManagerProtocol
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
