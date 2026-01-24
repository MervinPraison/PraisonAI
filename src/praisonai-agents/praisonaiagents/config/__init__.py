"""
Configuration Module for PraisonAI Agents.

Provides feature configuration classes for agent-centric API:
- MemoryConfig: Memory and session management
- KnowledgeConfig: RAG and knowledge retrieval
- PlanningConfig: Planning mode settings
- ReflectionConfig: Self-reflection settings
- GuardrailConfig: Safety and validation
- WebConfig: Web search and fetch

Also provides:
- Unified parameter resolver (resolve function)
- Preset registries
- Parse utilities

All imports are lazy-loaded for zero performance impact.
"""

__all__ = [
    # Enums
    "MemoryBackend",
    "ChunkingStrategy",
    "GuardrailAction",
    "WebSearchProvider",
    "OutputPreset",
    "ExecutionPreset",
    # Config classes
    "MemoryConfig",
    "KnowledgeConfig",
    "PlanningConfig",
    "MultiAgentPlanningConfig",
    "ReflectionConfig",
    "GuardrailConfig",
    "WebConfig",
    "OutputConfig",
    "ExecutionConfig",
    "TemplateConfig",
    "CachingConfig",
    "HooksConfig",
    "SkillsConfig",
    # Type aliases
    "MemoryParam",
    "KnowledgeParam",
    "PlanningParam",
    "ReflectionParam",
    "GuardrailParam",
    "WebParam",
    # Resolver
    "resolve",
    "ArrayMode",
    # Convenience resolvers
    "resolve_memory",
    "resolve_knowledge",
    "resolve_output",
    "resolve_execution",
    "resolve_web",
    "resolve_planning",
    "resolve_reflection",
    "resolve_context",
    "resolve_autonomy",
    "resolve_caching",
    "resolve_hooks",
    "resolve_skills",
    "resolve_routing",
    # Parse utilities
    "detect_url_scheme",
    "is_path_like",
    "suggest_similar",
    # Presets
    "MEMORY_PRESETS",
    "MEMORY_URL_SCHEMES",
    "OUTPUT_PRESETS",
    "EXECUTION_PRESETS",
    "WEB_PRESETS",
    "PLANNING_PRESETS",
    "REFLECTION_PRESETS",
    "CONTEXT_PRESETS",
    "AUTONOMY_PRESETS",
    "CACHING_PRESETS",
]

# Module mapping for lazy loading
_MODULE_MAP = {
    # feature_configs
    "MemoryBackend": "feature_configs",
    "ChunkingStrategy": "feature_configs",
    "GuardrailAction": "feature_configs",
    "WebSearchProvider": "feature_configs",
    "OutputPreset": "feature_configs",
    "ExecutionPreset": "feature_configs",
    "MemoryConfig": "feature_configs",
    "KnowledgeConfig": "feature_configs",
    "PlanningConfig": "feature_configs",
    "MultiAgentPlanningConfig": "feature_configs",
    "ReflectionConfig": "feature_configs",
    "GuardrailConfig": "feature_configs",
    "WebConfig": "feature_configs",
    "OutputConfig": "feature_configs",
    "ExecutionConfig": "feature_configs",
    "TemplateConfig": "feature_configs",
    "CachingConfig": "feature_configs",
    "HooksConfig": "feature_configs",
    "SkillsConfig": "feature_configs",
    "MemoryParam": "feature_configs",
    "KnowledgeParam": "feature_configs",
    "PlanningParam": "feature_configs",
    "ReflectionParam": "feature_configs",
    "GuardrailParam": "feature_configs",
    "WebParam": "feature_configs",
    # param_resolver
    "resolve": "param_resolver",
    "ArrayMode": "param_resolver",
    "resolve_memory": "param_resolver",
    "resolve_knowledge": "param_resolver",
    "resolve_output": "param_resolver",
    "resolve_execution": "param_resolver",
    "resolve_web": "param_resolver",
    "resolve_planning": "param_resolver",
    "resolve_reflection": "param_resolver",
    "resolve_context": "param_resolver",
    "resolve_autonomy": "param_resolver",
    "resolve_caching": "param_resolver",
    "resolve_hooks": "param_resolver",
    "resolve_skills": "param_resolver",
    "resolve_routing": "param_resolver",
    # parse_utils
    "detect_url_scheme": "parse_utils",
    "is_path_like": "parse_utils",
    "suggest_similar": "parse_utils",
    # presets
    "MEMORY_PRESETS": "presets",
    "MEMORY_URL_SCHEMES": "presets",
    "OUTPUT_PRESETS": "presets",
    "EXECUTION_PRESETS": "presets",
    "WEB_PRESETS": "presets",
    "PLANNING_PRESETS": "presets",
    "REFLECTION_PRESETS": "presets",
    "CONTEXT_PRESETS": "presets",
    "AUTONOMY_PRESETS": "presets",
    "CACHING_PRESETS": "presets",
}


def __getattr__(name: str):
    """Lazy load config classes and utilities."""
    if name in _MODULE_MAP:
        module_name = _MODULE_MAP[name]
        import importlib
        module = importlib.import_module(f".{module_name}", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
