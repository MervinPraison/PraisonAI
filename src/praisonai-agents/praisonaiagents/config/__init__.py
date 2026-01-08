"""
Configuration Module for PraisonAI Agents.

Provides feature configuration classes for agent-centric API:
- MemoryConfig: Memory and session management
- KnowledgeConfig: RAG and knowledge retrieval
- PlanningConfig: Planning mode settings
- ReflectionConfig: Self-reflection settings
- GuardrailConfig: Safety and validation
- WebConfig: Web search and fetch

All imports are lazy-loaded for zero performance impact.
"""

__all__ = [
    # Enums
    "MemoryBackend",
    "ChunkingStrategy",
    "GuardrailAction",
    "WebSearchProvider",
    # Config classes
    "MemoryConfig",
    "KnowledgeConfig",
    "PlanningConfig",
    "ReflectionConfig",
    "GuardrailConfig",
    "WebConfig",
    # Type aliases
    "MemoryParam",
    "KnowledgeParam",
    "PlanningParam",
    "ReflectionParam",
    "GuardrailParam",
    "WebParam",
]


def __getattr__(name: str):
    """Lazy load config classes."""
    if name in __all__:
        from . import feature_configs
        return getattr(feature_configs, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
