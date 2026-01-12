"""
Learn Module - Continuous Learning within Memory System.

Provides learning capabilities for agents to capture patterns, preferences,
and insights from interactions to improve future responses.

Usage:
    from praisonaiagents import Agent, MemoryConfig, LearnConfig
    
    # Simple enable
    agent = Agent(memory=MemoryConfig(learn=True))
    
    # With specific capabilities
    agent = Agent(memory=MemoryConfig(
        learn=LearnConfig(
            persona=True,
            insights=True,
            patterns=True,
        )
    ))
"""

__all__ = [
    "LearnManager",
    "PersonaStore",
    "InsightStore",
    "ThreadStore",
    "PatternStore",
    "DecisionStore",
    "FeedbackStore",
    "ImprovementStore",
]


def __getattr__(name: str):
    """Lazy loading for learn module components."""
    if name == "LearnManager":
        from .manager import LearnManager
        return LearnManager
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
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
