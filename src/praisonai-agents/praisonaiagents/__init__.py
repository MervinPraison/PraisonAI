"""
Praison AI Agents - A package for hierarchical AI agent task execution

This module uses lazy loading to minimize import time and memory usage.
Heavy dependencies like litellm are only loaded when actually needed.
"""

# =============================================================================
# NAMING CONVENTION GUIDE (Simplified patterns for consistency)
# =============================================================================
# | Pattern       | When to Use             | Examples                        |
# |---------------|-------------------------|----------------------------------|
# | add_X         | Register something      | add_hook, add_tool, add_profile |
# | get_X         | Retrieve something      | get_tool, get_profile           |
# | remove_X      | Unregister something    | remove_hook, remove_tool        |
# | has_X         | Check existence         | has_hook, has_tool              |
# | list_X        | List all items          | list_tools, list_profiles       |
# | enable_X      | Turn on feature         | enable_telemetry                |
# | disable_X     | Turn off feature        | disable_telemetry               |
# | XConfig       | Configuration class     | MemoryConfig, HooksConfig       |
# | @decorator    | Decorator               | @tool, @add_hook                |
# |---------------|-------------------------|----------------------------------|
# | set_default_X | Internal/advanced only  | (don't simplify - internal)     |
# | create_X      | Factory function        | (already well-named)            |
# =============================================================================

# =============================================================================
# NAMESPACE PACKAGE GUARD
# =============================================================================
# Detect if we're loaded as a namespace package (which indicates stale artifacts
# in site-packages). This happens when there's a praisonaiagents/ directory in
# site-packages without an __init__.py file.
#
# Root cause: Partial uninstall or version mismatch leaves directories that
# Python's PathFinder treats as namespace packages, shadowing the real package.
# =============================================================================
if __file__ is None:
    import warnings as _ns_warnings
    _ns_warnings.warn(
        "praisonaiagents is loaded as a namespace package, which indicates "
        "stale artifacts in site-packages. This will cause import errors. "
        "Fix: Remove the stale directory with:\n"
        "  rm -rf $(python -c \"import site; print(site.getsitepackages()[0])\")/praisonaiagents/\n"
        "Then reinstall: pip install praisonaiagents",
        ImportWarning,
        stacklevel=1
    )
    del _ns_warnings

# Apply warning patch BEFORE any imports to intercept warnings at the source
from . import _warning_patch  # noqa: F401

# Import centralized logging configuration FIRST
from . import _logging

# Configure root logger after logging is initialized
_logging.configure_root_logger()

# Import configuration (lightweight, no heavy deps)
from . import _config

# Lightweight imports that don't trigger heavy dependency chains
from .tools.tools import Tools
from .tools.base import BaseTool, ToolResult, ToolValidationError, validate_tool
from .tools.decorator import tool, FunctionTool
from .tools.registry import get_registry, register_tool, get_tool, ToolRegistry
# db and obs are lazy-loaded via __getattr__ for performance

# Sub-packages for organized imports (pa.config, pa.tools, etc.)
# These enable: import praisonaiagents as pa; pa.config.MemoryConfig
from . import config
from . import tools
# Note: db, obs, knowledge and mcp are lazy-loaded via __getattr__ due to heavy deps

# Embedding API - LAZY LOADED via __getattr__ for performance
# Supports: embedding, embeddings, aembedding, aembeddings, EmbeddingResult, get_dimensions

# Workflows - LAZY LOADED (moved to __getattr__)
# Workflow, Task, WorkflowContext, StepResult, Route, Parallel, Loop, Repeat, etc.

# Guardrails - LAZY LOADED (imports main.py which imports rich)
# GuardrailResult and LLMGuardrail moved to __getattr__

# Handoff - LAZY LOADED (moved to __getattr__)
# Handoff, handoff, handoff_filters, etc.

# Flow display - LAZY LOADED (moved to __getattr__)
# FlowDisplay and track_workflow are now lazy loaded

# Main display utilities - LAZY LOADED to avoid importing rich at startup
# These are only needed when output=verbose, not for silent mode
# Moved to __getattr__ for lazy loading

# ============================================================================
# LAZY LOADING CONFIGURATION
# ============================================================================
# Using centralized _lazy.py utility for DRY, thread-safe lazy loading.
# All heavy dependencies are loaded on-demand to minimize import time.
# ============================================================================

from ._lazy import lazy_import, create_lazy_getattr_with_fallback

# Thread-safe cache for lazy-loaded values
_lazy_cache = {}

# Backward compatibility: _get_lazy_cache function for tests
import threading
_lazy_cache_local = threading.local()

def _get_lazy_cache():
    """Get thread-local lazy cache dict. Thread-safe for concurrent access.
    
    Note: This is kept for backward compatibility with tests.
    The main lazy loading now uses the centralized _lazy.py utility.
    """
    if not hasattr(_lazy_cache_local, 'cache'):
        _lazy_cache_local.cache = {}
    return _lazy_cache_local.cache

# ============================================================================
# LAZY IMPORT MAPPING
# ============================================================================
# Maps attribute names to (module_path, attr_name) tuples.
# This is the single source of truth for all lazy imports.
# ============================================================================

_LAZY_IMPORTS = {
    # Main display utilities (imports rich)
    'TaskOutput': ('praisonaiagents.main', 'TaskOutput'),
    'ReflectionOutput': ('praisonaiagents.main', 'ReflectionOutput'),
    'display_interaction': ('praisonaiagents.main', 'display_interaction'),
    'display_self_reflection': ('praisonaiagents.main', 'display_self_reflection'),
    'display_instruction': ('praisonaiagents.main', 'display_instruction'),
    'display_tool_call': ('praisonaiagents.main', 'display_tool_call'),
    'display_error': ('praisonaiagents.main', 'display_error'),
    'display_generating': ('praisonaiagents.main', 'display_generating'),
    'clean_triple_backticks': ('praisonaiagents.main', 'clean_triple_backticks'),
    'error_logs': ('praisonaiagents.main', 'error_logs'),
    'register_display_callback': ('praisonaiagents.main', 'register_display_callback'),
    'sync_display_callbacks': ('praisonaiagents.main', 'sync_display_callbacks'),
    'async_display_callbacks': ('praisonaiagents.main', 'async_display_callbacks'),
    
    # Workflows
    'Workflow': ('praisonaiagents.workflows', 'Workflow'),
    'Task': ('praisonaiagents.workflows', 'Task'),
    'WorkflowContext': ('praisonaiagents.workflows', 'WorkflowContext'),
    'StepResult': ('praisonaiagents.workflows', 'StepResult'),
    'Route': ('praisonaiagents.workflows', 'Route'),
    'Parallel': ('praisonaiagents.workflows', 'Parallel'),
    'Loop': ('praisonaiagents.workflows', 'Loop'),
    'Repeat': ('praisonaiagents.workflows', 'Repeat'),
    'route': ('praisonaiagents.workflows', 'route'),
    'parallel': ('praisonaiagents.workflows', 'parallel'),
    'loop': ('praisonaiagents.workflows', 'loop'),
    'repeat': ('praisonaiagents.workflows', 'repeat'),
    'Pipeline': ('praisonaiagents.workflows', 'Pipeline'),
    
    # Handoff
    'Handoff': ('praisonaiagents.agent.handoff', 'Handoff'),
    'handoff': ('praisonaiagents.agent.handoff', 'handoff'),
    'handoff_filters': ('praisonaiagents.agent.handoff', 'handoff_filters'),
    'RECOMMENDED_PROMPT_PREFIX': ('praisonaiagents.agent.handoff', 'RECOMMENDED_PROMPT_PREFIX'),
    'prompt_with_handoff_instructions': ('praisonaiagents.agent.handoff', 'prompt_with_handoff_instructions'),
    'HandoffConfig': ('praisonaiagents.agent.handoff', 'HandoffConfig'),
    'HandoffResult': ('praisonaiagents.agent.handoff', 'HandoffResult'),
    'HandoffInputData': ('praisonaiagents.agent.handoff', 'HandoffInputData'),
    'ContextPolicy': ('praisonaiagents.agent.handoff', 'ContextPolicy'),
    'HandoffError': ('praisonaiagents.agent.handoff', 'HandoffError'),
    'HandoffCycleError': ('praisonaiagents.agent.handoff', 'HandoffCycleError'),
    'HandoffDepthError': ('praisonaiagents.agent.handoff', 'HandoffDepthError'),
    'HandoffTimeoutError': ('praisonaiagents.agent.handoff', 'HandoffTimeoutError'),
    
    # Embedding API
    'embedding': ('praisonaiagents.embedding.embed', 'embedding'),
    'embeddings': ('praisonaiagents.embedding.embed', 'embedding'),
    'aembedding': ('praisonaiagents.embedding.embed', 'aembedding'),
    'aembeddings': ('praisonaiagents.embedding.embed', 'aembedding'),
    'embed': ('praisonaiagents.embedding.embed', 'embed'),
    'aembed': ('praisonaiagents.embedding.embed', 'aembed'),
    'EmbeddingResult': ('praisonaiagents.embedding.result', 'EmbeddingResult'),
    'get_dimensions': ('praisonaiagents.embedding.dimensions', 'get_dimensions'),
    
    # Guardrails
    'GuardrailResult': ('praisonaiagents.guardrails', 'GuardrailResult'),
    'LLMGuardrail': ('praisonaiagents.guardrails', 'LLMGuardrail'),
    
    # Flow display
    'FlowDisplay': ('praisonaiagents.flow_display', 'FlowDisplay'),
    'track_workflow': ('praisonaiagents.flow_display', 'track_workflow'),
    
    # Agent classes
    'Agent': ('praisonaiagents.agent.agent', 'Agent'),
    'ImageAgent': ('praisonaiagents.agent.image_agent', 'ImageAgent'),
    'VideoAgent': ('praisonaiagents.agent.video_agent', 'VideoAgent'),
    'VideoConfig': ('praisonaiagents.agent.video_agent', 'VideoConfig'),
    'AudioAgent': ('praisonaiagents.agent.audio_agent', 'AudioAgent'),
    'AudioConfig': ('praisonaiagents.agent.audio_agent', 'AudioConfig'),
    'OCRAgent': ('praisonaiagents.agent.ocr_agent', 'OCRAgent'),
    'OCRConfig': ('praisonaiagents.agent.ocr_agent', 'OCRConfig'),
    'ContextAgent': ('praisonaiagents.agent.context_agent', 'ContextAgent'),
    'create_context_agent': ('praisonaiagents.agent.context_agent', 'create_context_agent'),
    'DeepResearchAgent': ('praisonaiagents.agent.deep_research_agent', 'DeepResearchAgent'),
    'DeepResearchResponse': ('praisonaiagents.agent.deep_research_agent', 'DeepResearchResponse'),
    'ReasoningStep': ('praisonaiagents.agent.deep_research_agent', 'ReasoningStep'),
    'WebSearchCall': ('praisonaiagents.agent.deep_research_agent', 'WebSearchCall'),
    'CodeExecutionStep': ('praisonaiagents.agent.deep_research_agent', 'CodeExecutionStep'),
    'MCPCall': ('praisonaiagents.agent.deep_research_agent', 'MCPCall'),
    'FileSearchCall': ('praisonaiagents.agent.deep_research_agent', 'FileSearchCall'),
    'Provider': ('praisonaiagents.agent.deep_research_agent', 'Provider'),
    'QueryRewriterAgent': ('praisonaiagents.agent.query_rewriter_agent', 'QueryRewriterAgent'),
    'RewriteStrategy': ('praisonaiagents.agent.query_rewriter_agent', 'RewriteStrategy'),
    'RewriteResult': ('praisonaiagents.agent.query_rewriter_agent', 'RewriteResult'),
    'PromptExpanderAgent': ('praisonaiagents.agent.prompt_expander_agent', 'PromptExpanderAgent'),
    'ExpandStrategy': ('praisonaiagents.agent.prompt_expander_agent', 'ExpandStrategy'),
    'ExpandResult': ('praisonaiagents.agent.prompt_expander_agent', 'ExpandResult'),
    'VisionAgent': ('praisonaiagents.agent.vision_agent', 'VisionAgent'),
    'VisionConfig': ('praisonaiagents.agent.vision_agent', 'VisionConfig'),
    'EmbeddingAgent': ('praisonaiagents.agent.embedding_agent', 'EmbeddingAgent'),
    'EmbeddingConfig': ('praisonaiagents.agent.embedding_agent', 'EmbeddingConfig'),
    'RealtimeAgent': ('praisonaiagents.agent.realtime_agent', 'RealtimeAgent'),
    'RealtimeConfig': ('praisonaiagents.agent.realtime_agent', 'RealtimeConfig'),
    'CodeAgent': ('praisonaiagents.agent.code_agent', 'CodeAgent'),
    'CodeConfig': ('praisonaiagents.agent.code_agent', 'CodeConfig'),
    
    # Agents / AgentManager
    'AgentManager': ('praisonaiagents.agents.agents', 'AgentManager'),
    # Note: 'Agents' is handled by _custom_handler for deprecation warning
    'Task': ('praisonaiagents.task.task', 'Task'),
    'AutoAgents': ('praisonaiagents.agents.autoagents', 'AutoAgents'),
    'AutoRagAgent': ('praisonaiagents.agents.auto_rag_agent', 'AutoRagAgent'),
    'AutoRagConfig': ('praisonaiagents.agents.auto_rag_agent', 'AutoRagConfig'),
    'RagRetrievalPolicy': ('praisonaiagents.agents.auto_rag_agent', 'RetrievalPolicy'),
    
    # Session
    'Session': ('praisonaiagents.session', 'Session'),
    
    # App (AgentApp protocol and config)
    'AgentAppProtocol': ('praisonaiagents.app.protocols', 'AgentAppProtocol'),
    'AgentAppConfig': ('praisonaiagents.app.config', 'AgentAppConfig'),
    
    # MCP (optional)
    'MCP': ('praisonaiagents.mcp.mcp', 'MCP'),
    
    # Knowledge
    'Knowledge': ('praisonaiagents.knowledge.knowledge', 'Knowledge'),
    'Chunking': ('praisonaiagents.knowledge.chunking', 'Chunking'),
    
    # FastContext
    'FastContext': ('praisonaiagents.context.fast', 'FastContext'),
    'FastContextResult': ('praisonaiagents.context.fast', 'FastContextResult'),
    'FileMatch': ('praisonaiagents.context.fast', 'FileMatch'),
    'LineRange': ('praisonaiagents.context.fast', 'LineRange'),
    
    # RAG
    'RetrievalConfig': ('praisonaiagents.rag.retrieval_config', 'RetrievalConfig'),
    'RetrievalPolicy': ('praisonaiagents.rag.retrieval_config', 'RetrievalPolicy'),
    'CitationsMode': ('praisonaiagents.rag.retrieval_config', 'CitationsMode'),
    'ContextPack': ('praisonaiagents.rag.models', 'ContextPack'),
    'RAGResult': ('praisonaiagents.rag', 'RAGResult'),
    'Citation': ('praisonaiagents.rag', 'Citation'),
    'RAG': ('praisonaiagents.rag', 'RAG'),
    'RAGConfig': ('praisonaiagents.rag', 'RAGConfig'),
    'RAGCitation': ('praisonaiagents.rag', 'Citation'),
    
    # Skills
    'SkillManager': ('praisonaiagents.skills', 'SkillManager'),
    'SkillProperties': ('praisonaiagents.skills', 'SkillProperties'),
    'SkillMetadata': ('praisonaiagents.skills', 'SkillMetadata'),
    'SkillLoader': ('praisonaiagents.skills', 'SkillLoader'),
    
    # Memory
    'Memory': ('praisonaiagents.memory.memory', 'Memory'),
    
    # Planning
    'Plan': ('praisonaiagents.planning', 'Plan'),
    'PlanStep': ('praisonaiagents.planning', 'PlanStep'),
    'TodoList': ('praisonaiagents.planning', 'TodoList'),
    'TodoItem': ('praisonaiagents.planning', 'TodoItem'),
    'PlanStorage': ('praisonaiagents.planning', 'PlanStorage'),
    'PlanningAgent': ('praisonaiagents.planning', 'PlanningAgent'),
    'ApprovalCallback': ('praisonaiagents.planning', 'ApprovalCallback'),
    'READ_ONLY_TOOLS': ('praisonaiagents.planning', 'READ_ONLY_TOOLS'),
    'RESTRICTED_TOOLS': ('praisonaiagents.planning', 'RESTRICTED_TOOLS'),
    
    # Trace (protocol-driven, for custom sinks) - AGENTS.md naming: XProtocol
    'ContextTraceSinkProtocol': ('praisonaiagents.trace', 'ContextTraceSinkProtocol'),
    'ContextTraceSink': ('praisonaiagents.trace', 'ContextTraceSink'),  # Backward compat alias
    'TraceSinkProtocol': ('praisonaiagents.trace', 'TraceSinkProtocol'),
    'TraceSink': ('praisonaiagents.trace', 'TraceSink'),  # Backward compat alias
    'ContextTraceEmitter': ('praisonaiagents.trace', 'ContextTraceEmitter'),
    'ContextEvent': ('praisonaiagents.trace', 'ContextEvent'),
    'ContextEventType': ('praisonaiagents.trace', 'ContextEventType'),
    'trace_context': ('praisonaiagents.trace', 'trace_context'),
    'ContextListSink': ('praisonaiagents.trace', 'ContextListSink'),
    'ContextNoOpSink': ('praisonaiagents.trace', 'ContextNoOpSink'),
    
    # Telemetry
    'get_telemetry': ('praisonaiagents.telemetry', 'get_telemetry'),
    'enable_telemetry': ('praisonaiagents.telemetry', 'enable_telemetry'),
    'disable_telemetry': ('praisonaiagents.telemetry', 'disable_telemetry'),
    'enable_performance_mode': ('praisonaiagents.telemetry', 'enable_performance_mode'),
    'disable_performance_mode': ('praisonaiagents.telemetry', 'disable_performance_mode'),
    'cleanup_telemetry_resources': ('praisonaiagents.telemetry', 'cleanup_telemetry_resources'),
    'MinimalTelemetry': ('praisonaiagents.telemetry', 'MinimalTelemetry'),
    'TelemetryCollector': ('praisonaiagents.telemetry', 'TelemetryCollector'),
    
    # UI (optional)
    'AGUI': ('praisonaiagents.ui.agui', 'AGUI'),
    'A2A': ('praisonaiagents.ui.a2a', 'A2A'),
    
    # Feature configs
    'MemoryConfig': ('praisonaiagents.config.feature_configs', 'MemoryConfig'),
    'KnowledgeConfig': ('praisonaiagents.config.feature_configs', 'KnowledgeConfig'),
    'PlanningConfig': ('praisonaiagents.config.feature_configs', 'PlanningConfig'),
    'ReflectionConfig': ('praisonaiagents.config.feature_configs', 'ReflectionConfig'),
    'GuardrailConfig': ('praisonaiagents.config.feature_configs', 'GuardrailConfig'),
    'WebConfig': ('praisonaiagents.config.feature_configs', 'WebConfig'),
    'OutputConfig': ('praisonaiagents.config.feature_configs', 'OutputConfig'),
    'ExecutionConfig': ('praisonaiagents.config.feature_configs', 'ExecutionConfig'),
    'TemplateConfig': ('praisonaiagents.config.feature_configs', 'TemplateConfig'),
    'CachingConfig': ('praisonaiagents.config.feature_configs', 'CachingConfig'),
    'HooksConfig': ('praisonaiagents.config.feature_configs', 'HooksConfig'),
    'SkillsConfig': ('praisonaiagents.config.feature_configs', 'SkillsConfig'),
    'AutonomyConfig': ('praisonaiagents.config.feature_configs', 'AutonomyConfig'),
    'MemoryBackend': ('praisonaiagents.config.feature_configs', 'MemoryBackend'),
    'ChunkingStrategy': ('praisonaiagents.config.feature_configs', 'ChunkingStrategy'),
    'GuardrailAction': ('praisonaiagents.config.feature_configs', 'GuardrailAction'),
    'WebSearchProvider': ('praisonaiagents.config.feature_configs', 'WebSearchProvider'),
    'OutputPreset': ('praisonaiagents.config.feature_configs', 'OutputPreset'),
    'ExecutionPreset': ('praisonaiagents.config.feature_configs', 'ExecutionPreset'),
    'AutonomyLevel': ('praisonaiagents.config.feature_configs', 'AutonomyLevel'),
    'MultiAgentHooksConfig': ('praisonaiagents.config.feature_configs', 'MultiAgentHooksConfig'),
    'MultiAgentOutputConfig': ('praisonaiagents.config.feature_configs', 'MultiAgentOutputConfig'),
    'MultiAgentExecutionConfig': ('praisonaiagents.config.feature_configs', 'MultiAgentExecutionConfig'),
    'MultiAgentPlanningConfig': ('praisonaiagents.config.feature_configs', 'MultiAgentPlanningConfig'),
    'MultiAgentMemoryConfig': ('praisonaiagents.config.feature_configs', 'MultiAgentMemoryConfig'),
    
    # Parameter resolver
    'resolve': ('praisonaiagents.config.param_resolver', 'resolve'),
    'ArrayMode': ('praisonaiagents.config.param_resolver', 'ArrayMode'),
    'resolve_memory': ('praisonaiagents.config.param_resolver', 'resolve_memory'),
    'resolve_knowledge': ('praisonaiagents.config.param_resolver', 'resolve_knowledge'),
    'resolve_output': ('praisonaiagents.config.param_resolver', 'resolve_output'),
    'resolve_execution': ('praisonaiagents.config.param_resolver', 'resolve_execution'),
    'resolve_web': ('praisonaiagents.config.param_resolver', 'resolve_web'),
    'resolve_planning': ('praisonaiagents.config.param_resolver', 'resolve_planning'),
    'resolve_reflection': ('praisonaiagents.config.param_resolver', 'resolve_reflection'),
    'resolve_context': ('praisonaiagents.config.param_resolver', 'resolve_context'),
    'resolve_autonomy': ('praisonaiagents.config.param_resolver', 'resolve_autonomy'),
    'resolve_caching': ('praisonaiagents.config.param_resolver', 'resolve_caching'),
    'resolve_hooks': ('praisonaiagents.config.param_resolver', 'resolve_hooks'),
    'resolve_skills': ('praisonaiagents.config.param_resolver', 'resolve_skills'),
    'resolve_routing': ('praisonaiagents.config.param_resolver', 'resolve_routing'),
    'resolve_guardrails': ('praisonaiagents.config.param_resolver', 'resolve_guardrails'),
    'resolve_guardrail_policies': ('praisonaiagents.config.param_resolver', 'resolve_guardrail_policies'),
    
    # Presets
    'MEMORY_PRESETS': ('praisonaiagents.config.presets', 'MEMORY_PRESETS'),
    'MEMORY_URL_SCHEMES': ('praisonaiagents.config.presets', 'MEMORY_URL_SCHEMES'),
    'OUTPUT_PRESETS': ('praisonaiagents.config.presets', 'OUTPUT_PRESETS'),
    'EXECUTION_PRESETS': ('praisonaiagents.config.presets', 'EXECUTION_PRESETS'),
    'WEB_PRESETS': ('praisonaiagents.config.presets', 'WEB_PRESETS'),
    'PLANNING_PRESETS': ('praisonaiagents.config.presets', 'PLANNING_PRESETS'),
    'REFLECTION_PRESETS': ('praisonaiagents.config.presets', 'REFLECTION_PRESETS'),
    'CONTEXT_PRESETS': ('praisonaiagents.config.presets', 'CONTEXT_PRESETS'),
    'AUTONOMY_PRESETS': ('praisonaiagents.config.presets', 'AUTONOMY_PRESETS'),
    'CACHING_PRESETS': ('praisonaiagents.config.presets', 'CACHING_PRESETS'),
    'MULTI_AGENT_OUTPUT_PRESETS': ('praisonaiagents.config.presets', 'MULTI_AGENT_OUTPUT_PRESETS'),
    'MULTI_AGENT_EXECUTION_PRESETS': ('praisonaiagents.config.presets', 'MULTI_AGENT_EXECUTION_PRESETS'),
    'GUARDRAIL_PRESETS': ('praisonaiagents.config.presets', 'GUARDRAIL_PRESETS'),
    'KNOWLEDGE_PRESETS': ('praisonaiagents.config.presets', 'KNOWLEDGE_PRESETS'),
    
    # Parse utilities
    'detect_url_scheme': ('praisonaiagents.config.parse_utils', 'detect_url_scheme'),
    'is_path_like': ('praisonaiagents.config.parse_utils', 'is_path_like'),
    'suggest_similar': ('praisonaiagents.config.parse_utils', 'suggest_similar'),
    'is_policy_string': ('praisonaiagents.config.parse_utils', 'is_policy_string'),
    'parse_policy_string': ('praisonaiagents.config.parse_utils', 'parse_policy_string'),
    
    # Context management
    'ContextConfig': ('praisonaiagents.context.models', 'ContextConfig'),
    'OptimizerStrategy': ('praisonaiagents.context.models', 'OptimizerStrategy'),
    'ManagerConfig': ('praisonaiagents.context.manager', 'ManagerConfig'),
    'ContextManager': ('praisonaiagents.context.manager', 'ContextManager'),
    
    # db and obs modules
    'db': ('praisonaiagents.db', 'db'),
    'obs': ('praisonaiagents.obs', 'obs'),
    
    # Gateway protocols and config (implementations in praisonai wrapper)
    'GatewayProtocol': ('praisonaiagents.gateway.protocols', 'GatewayProtocol'),
    'GatewaySessionProtocol': ('praisonaiagents.gateway.protocols', 'GatewaySessionProtocol'),
    'GatewayClientProtocol': ('praisonaiagents.gateway.protocols', 'GatewayClientProtocol'),
    'GatewayEvent': ('praisonaiagents.gateway.protocols', 'GatewayEvent'),
    'GatewayMessage': ('praisonaiagents.gateway.protocols', 'GatewayMessage'),
    'EventType': ('praisonaiagents.gateway.protocols', 'EventType'),
    'GatewayConfig': ('praisonaiagents.gateway.config', 'GatewayConfig'),
    'SessionConfig': ('praisonaiagents.gateway.config', 'SessionConfig'),
    
    # Bot protocols and config (implementations in praisonai wrapper)
    'BotProtocol': ('praisonaiagents.bots.protocols', 'BotProtocol'),
    'BotMessage': ('praisonaiagents.bots.protocols', 'BotMessage'),
    'BotUser': ('praisonaiagents.bots.protocols', 'BotUser'),
    'BotChannel': ('praisonaiagents.bots.protocols', 'BotChannel'),
    'MessageType': ('praisonaiagents.bots.protocols', 'MessageType'),
    'BotConfig': ('praisonaiagents.bots.config', 'BotConfig'),
    
    # Sandbox protocols and config (implementations in praisonai wrapper)
    'SandboxProtocol': ('praisonaiagents.sandbox.protocols', 'SandboxProtocol'),
    'SandboxResult': ('praisonaiagents.sandbox.protocols', 'SandboxResult'),
    'SandboxStatus': ('praisonaiagents.sandbox.protocols', 'SandboxStatus'),
    'ResourceLimits': ('praisonaiagents.sandbox.protocols', 'ResourceLimits'),
    'SandboxConfig': ('praisonaiagents.sandbox.config', 'SandboxConfig'),
    'SecurityPolicy': ('praisonaiagents.sandbox.config', 'SecurityPolicy'),
    
    # Model failover
    'AuthProfile': ('praisonaiagents.llm.failover', 'AuthProfile'),
    'ProviderStatus': ('praisonaiagents.llm.failover', 'ProviderStatus'),
    'FailoverConfig': ('praisonaiagents.llm.failover', 'FailoverConfig'),
    'FailoverManager': ('praisonaiagents.llm.failover', 'FailoverManager'),
}


def _custom_handler(name, cache):
    """Handle special cases that need custom logic."""
    import warnings
    
    # Agents is a silent alias for AgentManager
    if name == "Agents":
        value = lazy_import('praisonaiagents.agents.agents', 'AgentManager', cache)
        cache['AgentManager'] = value
        cache['Agents'] = value
        return value
    
    # Task removed in v4.0.0 - use Task instead
    if name == "Task":
        raise ImportError(
            "Task has been removed in v4.0.0. Use Task instead.\n"
            "Migration: Replace 'from praisonaiagents import Task' with 'from praisonaiagents import Task'\n"
            "Task supports all Task features including action, handler, loop_over, etc."
        )
    
    # Module imports (return the module itself)
    if name == 'memory':
        import importlib
        return importlib.import_module('.memory', 'praisonaiagents')
    if name == 'workflows':
        import importlib
        return importlib.import_module('.workflows', 'praisonaiagents')
    
    raise AttributeError(f"Not handled by custom_handler: {name}")


# ============================================================================
# SUBPACKAGE FUNCTION OVERRIDES
# ============================================================================
# Some subpackage names conflict with function names we want to export.
# Override them here to return the function instead of the module.
# ============================================================================

# Override 'embedding' to return the function, not the subpackage
from .embedding.embed import embedding as _embedding_func
embedding = _embedding_func

# Also provide embeddings alias
embeddings = _embedding_func


# Create the __getattr__ function using centralized utility
__getattr__ = create_lazy_getattr_with_fallback(
    mapping=_LAZY_IMPORTS,
    module_name=__name__,
    cache=_lazy_cache,
    fallback_modules=['tools', 'memory', 'config', 'workflows'],
    custom_handler=_custom_handler
)


# Initialize telemetry only if explicitly enabled via config
def _init_telemetry():
    """Initialize telemetry if enabled via environment variable."""
    if not _config.TELEMETRY_ENABLED:
        return
    
    try:
        from .telemetry import get_telemetry
        from .telemetry.integration import auto_instrument_all
        
        _telemetry = get_telemetry()
        if _telemetry and _telemetry.enabled:
            use_performance_mode = _config.PERFORMANCE_MODE and not (
                _config.FULL_TELEMETRY or _config.AUTO_INSTRUMENT
            )
            auto_instrument_all(_telemetry, performance_mode=use_performance_mode)
            
            # Track package import for basic usage analytics
            try:
                _telemetry.track_feature_usage("package_import")
            except Exception:
                pass
    except Exception:
        # Silently fail if there are any issues - never break user applications
        pass


# Only initialize telemetry if explicitly enabled
_init_telemetry()


def warmup(include_litellm: bool = False, include_openai: bool = True) -> dict:
    """
    Pre-import heavy dependencies to reduce first-call latency.
    
    NOTE: For default OpenAI usage (llm="gpt-4o-mini"), warmup is NOT needed.
    The default path uses the native OpenAI SDK which is fast (~100ms import).
    
    Warmup is only beneficial when using LiteLLM backend, which is triggered by:
    - Using "/" in model name (e.g., llm="openai/gpt-4o-mini")
    - Passing a dict config (e.g., llm={"model": "gpt-4o-mini"})
    - Using base_url parameter
    
    Args:
        include_litellm: Pre-import LiteLLM (~2-3s). Only needed for multi-provider support.
        include_openai: Pre-import OpenAI SDK (~100ms). Default path, usually fast.
    
    Returns:
        dict: Timing information for each component warmed up
    
    Example:
        # For LiteLLM multi-provider usage:
        from praisonaiagents import warmup
        warmup(include_litellm=True)  # Pre-load LiteLLM
        
        agent = Agent(llm="anthropic/claude-3-sonnet")  # Now faster
        
        # For default OpenAI usage, no warmup needed:
        agent = Agent(llm="gpt-4o-mini")  # Already fast!
    """
    import time
    timings = {}
    
    if include_openai:
        start = time.perf_counter()
        try:
            import openai
            timings['openai'] = (time.perf_counter() - start) * 1000
        except ImportError:
            timings['openai'] = -1  # Not available
    
    if include_litellm:
        start = time.perf_counter()
        try:
            import litellm
            # Also configure litellm to avoid first-call overhead
            litellm.telemetry = False
            litellm.set_verbose = False
            litellm.drop_params = True
            litellm.modify_params = True
            timings['litellm'] = (time.perf_counter() - start) * 1000
        except ImportError:
            timings['litellm'] = -1  # Not available
    
    return timings


# ============================================================================
# PUBLIC API: __all__ (controls IDE autocomplete and `from X import *`)
# ============================================================================
# DESIGN: Keep __all__ minimal for clean IDE experience.
# All 186+ symbols are still accessible via __getattr__ for backwards compat.
# Organized imports available via sub-packages: config, tools, memory, workflows
# ============================================================================

__all__ = [
    # Core classes - the essentials
    'Agent',
    'AgentManager',  # Primary class for multi-agent coordination (v0.14.16+)
    'Agents',  # Deprecated alias for AgentManager
    'Task',
    
    # Tool essentials
    'tool',
    'Tools',
    
    # Embedding API - simplified imports
    # Usage: from praisonaiagents import embedding, EmbeddingResult
    'embedding',
    'embeddings',  # Plural alias (OpenAI style)
    'aembedding',
    'aembeddings',  # Plural alias for async
    'EmbeddingResult',
    'get_dimensions',
    
    # Sub-packages for organized imports
    # Usage: import praisonaiagents as pa; pa.config.MemoryConfig
    'config',
    'tools',
    'memory',
    'workflows',
]


def __dir__():
    """
    Return clean list for dir() - matches __all__ plus standard attributes.
    
    This keeps IDE autocomplete clean while preserving full backwards
    compatibility via __getattr__ for all 186+ legacy exports.
    """
    return list(__all__) + [
        # Standard module attributes
        '__name__', '__doc__', '__file__', '__path__', '__package__',
        '__loader__', '__spec__', '__cached__', '__builtins__',
    ]


# ============================================================================
# BACKWARDS COMPATIBILITY: Legacy __all__ items (for reference)
# ============================================================================
# All items below are still importable via __getattr__ but NOT in autocomplete:
# - ImageAgent, ContextAgent, create_context_agent, PraisonAIAgents
# - BaseTool, ToolResult, ToolValidationError, validate_tool, FunctionTool
# - ToolRegistry, get_registry, register_tool, get_tool
# - TaskOutput, ReflectionOutput, AutoAgents, AutoRagAgent, AutoRagConfig
# - Session, Memory, db, obs, Knowledge, Chunking
# - GuardrailResult, LLMGuardrail, Handoff, handoff, handoff_filters
# - MemoryConfig, KnowledgeConfig, PlanningConfig, OutputConfig, etc.
# - Workflow, Task, Route, Parallel, Loop, Repeat, Pipeline, etc.
# - MCP, FlowDisplay, track_workflow, FastContext, etc.
# - Plan, PlanStep, TodoList, PlanningAgent, ApprovalCallback, etc.
# - RAG, RAGConfig, RAGResult, AGUI, A2A, etc.
# - All telemetry, display, and utility functions
# ============================================================================
