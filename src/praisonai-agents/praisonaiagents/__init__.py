"""
Praison AI Agents - A package for hierarchical AI agent task execution

This module uses lazy loading to minimize import time and memory usage.
Heavy dependencies like litellm are only loaded when actually needed.
"""

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
from .db import db
from .obs import obs

# Sub-packages for organized imports (pa.config, pa.tools, etc.)
# These enable: import praisonaiagents as pa; pa.config.MemoryConfig
from . import config
from . import tools
from . import memory
from . import workflows
# Note: knowledge and mcp are lazy-loaded via __getattr__ due to heavy deps

# Workflows - lightweight module
from .workflows import (
    Workflow, WorkflowStep, WorkflowContext, StepResult,
    Route, Parallel, Loop, Repeat,
    route, parallel, loop, repeat,
    Pipeline  # Alias for Workflow
)
from .guardrails import GuardrailResult, LLMGuardrail

# Handoff - lightweight (unified agent-to-agent transfer)
from .agent.handoff import (
    Handoff, handoff, handoff_filters, 
    RECOMMENDED_PROMPT_PREFIX, prompt_with_handoff_instructions,
    HandoffConfig, HandoffResult, HandoffInputData,
    ContextPolicy, HandoffError, HandoffCycleError, HandoffDepthError, HandoffTimeoutError,
)

# Flow display (optional)
try:
    from .flow_display import FlowDisplay, track_workflow
except ImportError:
    FlowDisplay = None
    track_workflow = None

# Main display utilities - these are used frequently so import directly
# but they don't pull in litellm
from .main import (
    TaskOutput,
    ReflectionOutput,
    display_interaction,
    display_self_reflection,
    display_instruction,
    display_tool_call,
    display_error,
    display_generating,
    clean_triple_backticks,
    error_logs,
    register_display_callback,
    sync_display_callbacks,
    async_display_callbacks,
)

# Module-level caches for lazy-loaded classes
_lazy_cache = {}

# Flags for optional modules
_mcp_available = None
_planning_available = None
_telemetry_available = None
_agui_available = None
_a2a_available = None


def __getattr__(name):
    """
    Lazy load heavy modules to avoid impacting package load time.
    
    This function is called when an attribute is not found in the module.
    It enables deferred loading of heavy dependencies like litellm.
    """
    global _mcp_available, _planning_available, _telemetry_available
    global _agui_available, _a2a_available
    
    # Return cached values if available
    if name in _lazy_cache:
        return _lazy_cache[name]
    
    # Agent and related classes (triggers litellm import chain)
    if name == "Agent":
        from .agent.agent import Agent
        _lazy_cache[name] = Agent
        return Agent
    elif name == "ImageAgent":
        from .agent.image_agent import ImageAgent
        _lazy_cache[name] = ImageAgent
        return ImageAgent
    elif name == "ContextAgent":
        from .agent.context_agent import ContextAgent
        _lazy_cache[name] = ContextAgent
        return ContextAgent
    elif name == "create_context_agent":
        from .agent.context_agent import create_context_agent
        _lazy_cache[name] = create_context_agent
        return create_context_agent
    elif name == "DeepResearchAgent":
        from .agent.deep_research_agent import DeepResearchAgent
        _lazy_cache[name] = DeepResearchAgent
        return DeepResearchAgent
    elif name == "DeepResearchResponse":
        from .agent.deep_research_agent import DeepResearchResponse
        _lazy_cache[name] = DeepResearchResponse
        return DeepResearchResponse
    elif name == "Citation":
        from .agent.deep_research_agent import Citation
        _lazy_cache[name] = Citation
        return Citation
    elif name == "ReasoningStep":
        from .agent.deep_research_agent import ReasoningStep
        _lazy_cache[name] = ReasoningStep
        return ReasoningStep
    elif name == "WebSearchCall":
        from .agent.deep_research_agent import WebSearchCall
        _lazy_cache[name] = WebSearchCall
        return WebSearchCall
    elif name == "CodeExecutionStep":
        from .agent.deep_research_agent import CodeExecutionStep
        _lazy_cache[name] = CodeExecutionStep
        return CodeExecutionStep
    elif name == "MCPCall":
        from .agent.deep_research_agent import MCPCall
        _lazy_cache[name] = MCPCall
        return MCPCall
    elif name == "FileSearchCall":
        from .agent.deep_research_agent import FileSearchCall
        _lazy_cache[name] = FileSearchCall
        return FileSearchCall
    elif name == "Provider":
        from .agent.deep_research_agent import Provider
        _lazy_cache[name] = Provider
        return Provider
    elif name == "QueryRewriterAgent":
        from .agent.query_rewriter_agent import QueryRewriterAgent
        _lazy_cache[name] = QueryRewriterAgent
        return QueryRewriterAgent
    elif name == "RewriteStrategy":
        from .agent.query_rewriter_agent import RewriteStrategy
        _lazy_cache[name] = RewriteStrategy
        return RewriteStrategy
    elif name == "RewriteResult":
        from .agent.query_rewriter_agent import RewriteResult
        _lazy_cache[name] = RewriteResult
        return RewriteResult
    elif name == "PromptExpanderAgent":
        from .agent.prompt_expander_agent import PromptExpanderAgent
        _lazy_cache[name] = PromptExpanderAgent
        return PromptExpanderAgent
    elif name == "ExpandStrategy":
        from .agent.prompt_expander_agent import ExpandStrategy
        _lazy_cache[name] = ExpandStrategy
        return ExpandStrategy
    elif name == "ExpandResult":
        from .agent.prompt_expander_agent import ExpandResult
        _lazy_cache[name] = ExpandResult
        return ExpandResult
    
    # Agents (canonical) and PraisonAIAgents (backward-compatible alias)
    elif name == "Agents":
        from .agents.agents import Agents
        _lazy_cache[name] = Agents
        _lazy_cache["PraisonAIAgents"] = Agents  # Also cache alias
        return Agents
    elif name == "PraisonAIAgents":
        import warnings
        warnings.warn(
            "PraisonAIAgents is deprecated, use Agents instead. "
            "Example: from praisonaiagents import Agents",
            DeprecationWarning,
            stacklevel=2
        )
        from .agents.agents import Agents
        _lazy_cache["Agents"] = Agents
        _lazy_cache[name] = Agents
        return Agents
    
    # Task
    elif name == "Task":
        from .task.task import Task
        _lazy_cache[name] = Task
        return Task
    
    # AutoAgents
    elif name == "AutoAgents":
        from .agents.autoagents import AutoAgents
        _lazy_cache[name] = AutoAgents
        return AutoAgents
    
    # AutoRagAgent (auto RAG retrieval decision)
    elif name == "AutoRagAgent":
        from .agents.auto_rag_agent import AutoRagAgent
        _lazy_cache[name] = AutoRagAgent
        return AutoRagAgent
    elif name == "AutoRagConfig":
        from .agents.auto_rag_agent import AutoRagConfig
        _lazy_cache[name] = AutoRagConfig
        return AutoRagConfig
    elif name == "RagRetrievalPolicy":
        from .agents.auto_rag_agent import RetrievalPolicy
        _lazy_cache[name] = RetrievalPolicy
        return RetrievalPolicy
    
    # Session (imports requests lazily via session/api.py)
    elif name == "Session":
        from .session import Session
        _lazy_cache[name] = Session
        return Session
    
    # MCP support (optional)
    elif name == "MCP":
        if _mcp_available is None:
            try:
                from .mcp.mcp import MCP as _MCP
                _lazy_cache[name] = _MCP
                return _MCP
            except ImportError:
                return None
        return _lazy_cache.get(name)
    
    # Knowledge module (imports chromadb, mem0)
    elif name == "Knowledge":
        from praisonaiagents.knowledge.knowledge import Knowledge
        _lazy_cache[name] = Knowledge
        return Knowledge
    elif name == "Chunking":
        from praisonaiagents.knowledge.chunking import Chunking
        _lazy_cache[name] = Chunking
        return Chunking
    
    # FastContext support
    elif name == "FastContext":
        from praisonaiagents.context.fast import FastContext
        _lazy_cache[name] = FastContext
        return FastContext
    elif name == "FastContextResult":
        from praisonaiagents.context.fast import FastContextResult
        _lazy_cache[name] = FastContextResult
        return FastContextResult
    elif name == "FileMatch":
        from praisonaiagents.context.fast import FileMatch
        _lazy_cache[name] = FileMatch
        return FileMatch
    elif name == "LineRange":
        from praisonaiagents.context.fast import LineRange
        _lazy_cache[name] = LineRange
        return LineRange
    
    # Retrieval configuration (Agent-first unified config)
    elif name == "RetrievalConfig":
        from praisonaiagents.rag.retrieval_config import RetrievalConfig
        _lazy_cache[name] = RetrievalConfig
        return RetrievalConfig
    elif name == "RetrievalPolicy":
        from praisonaiagents.rag.retrieval_config import RetrievalPolicy
        _lazy_cache[name] = RetrievalPolicy
        return RetrievalPolicy
    elif name == "CitationsMode":
        from praisonaiagents.rag.retrieval_config import CitationsMode
        _lazy_cache[name] = CitationsMode
        return CitationsMode
    
    # RAG models (used by Agent.query() and Agent.retrieve())
    elif name == "ContextPack":
        from praisonaiagents.rag.models import ContextPack
        _lazy_cache[name] = ContextPack
        return ContextPack
    elif name == "RAGResult":
        from praisonaiagents.rag import RAGResult
        _lazy_cache[name] = RAGResult
        return RAGResult
    elif name == "Citation":
        from praisonaiagents.rag import Citation
        _lazy_cache[name] = Citation
        return Citation
    
    # RAG internals (advanced use - prefer Agent.query() for normal usage)
    elif name == "RAG":
        from praisonaiagents.rag import RAG
        _lazy_cache[name] = RAG
        return RAG
    elif name == "RAGConfig":
        from praisonaiagents.rag import RAGConfig
        _lazy_cache[name] = RAGConfig
        return RAGConfig
    elif name == "RAGCitation":
        from praisonaiagents.rag import Citation
        _lazy_cache[name] = Citation
        return Citation
    
    # Agent Skills support (lazy loaded for zero performance impact)
    elif name == "SkillManager":
        from praisonaiagents.skills import SkillManager
        _lazy_cache[name] = SkillManager
        return SkillManager
    elif name == "SkillProperties":
        from praisonaiagents.skills import SkillProperties
        _lazy_cache[name] = SkillProperties
        return SkillProperties
    elif name == "SkillMetadata":
        from praisonaiagents.skills import SkillMetadata
        _lazy_cache[name] = SkillMetadata
        return SkillMetadata
    elif name == "SkillLoader":
        from praisonaiagents.skills import SkillLoader
        _lazy_cache[name] = SkillLoader
        return SkillLoader
    
    # Memory module (imports chromadb)
    elif name == "Memory":
        from praisonaiagents.memory.memory import Memory
        _lazy_cache[name] = Memory
        return Memory
    
    # Planning mode support (lazy)
    elif name in ("Plan", "PlanStep", "TodoList", "TodoItem", "PlanStorage", 
                  "PlanningAgent", "ApprovalCallback", "READ_ONLY_TOOLS", 
                  "RESTRICTED_TOOLS"):
        try:
            from . import planning as _planning
            result = getattr(_planning, name)
            _lazy_cache[name] = result
            return result
        except ImportError:
            if name in ("READ_ONLY_TOOLS", "RESTRICTED_TOOLS"):
                return []
            return None
    
    # Telemetry support (lazy loaded)
    elif name in ("get_telemetry", "enable_telemetry", "disable_telemetry",
                  "enable_performance_mode", "disable_performance_mode",
                  "cleanup_telemetry_resources", "MinimalTelemetry", "TelemetryCollector"):
        try:
            from . import telemetry as _telemetry
            result = getattr(_telemetry, name)
            _lazy_cache[name] = result
            return result
        except ImportError:
            # Provide stub functions
            if name == "get_telemetry":
                return lambda: None
            elif name == "enable_telemetry":
                import logging
                def _stub(*args, **kwargs):
                    logging.warning(
                        "Telemetry not available. Install with: pip install praisonaiagents[telemetry]"
                    )
                    return None
                return _stub
            elif name in ("disable_telemetry", "enable_performance_mode", 
                         "disable_performance_mode", "cleanup_telemetry_resources"):
                return lambda: None
            return None
    
    # AG-UI support (optional, lazy loaded)
    elif name == "AGUI":
        try:
            from praisonaiagents.ui.agui import AGUI
            _lazy_cache[name] = AGUI
            return AGUI
        except ImportError:
            return None
    
    # A2A support (optional, lazy loaded)
    elif name == "A2A":
        try:
            from praisonaiagents.ui.a2a import A2A
            _lazy_cache[name] = A2A
            return A2A
        except ImportError:
            return None
    
    # Feature Config classes (agent-centric API)
    elif name in ("MemoryConfig", "KnowledgeConfig", "PlanningConfig", 
                  "ReflectionConfig", "GuardrailConfig", "WebConfig",
                  "OutputConfig", "ExecutionConfig", "TemplateConfig",
                  "CachingConfig", "HooksConfig", "SkillsConfig", "AutonomyConfig",
                  "MemoryBackend", "ChunkingStrategy", "GuardrailAction", 
                  "WebSearchProvider", "OutputPreset", "ExecutionPreset", "AutonomyLevel",
                  # Multi-Agent config classes
                  "MultiAgentHooksConfig", "MultiAgentOutputConfig", 
                  "MultiAgentExecutionConfig", "MultiAgentPlanningConfig",
                  "MultiAgentMemoryConfig"):
        from .config import feature_configs
        result = getattr(feature_configs, name)
        _lazy_cache[name] = result
        return result
    
    # Unified parameter resolver (agent-centric API)
    elif name in ("resolve", "ArrayMode", "resolve_memory", "resolve_knowledge",
                  "resolve_output", "resolve_execution", "resolve_web",
                  "resolve_planning", "resolve_reflection", "resolve_context",
                  "resolve_autonomy", "resolve_caching", "resolve_hooks",
                  "resolve_skills", "resolve_routing", "resolve_guardrails",
                  "resolve_guardrail_policies"):
        from .config import param_resolver
        result = getattr(param_resolver, name)
        _lazy_cache[name] = result
        return result
    
    # Preset registries (agent-centric API)
    elif name in ("MEMORY_PRESETS", "MEMORY_URL_SCHEMES", "OUTPUT_PRESETS",
                  "EXECUTION_PRESETS", "WEB_PRESETS", "PLANNING_PRESETS",
                  "REFLECTION_PRESETS", "CONTEXT_PRESETS", "AUTONOMY_PRESETS",
                  "CACHING_PRESETS", "MULTI_AGENT_OUTPUT_PRESETS",
                  "MULTI_AGENT_EXECUTION_PRESETS", "GUARDRAIL_PRESETS",
                  "KNOWLEDGE_PRESETS"):
        from .config import presets
        result = getattr(presets, name)
        _lazy_cache[name] = result
        return result
    
    # Parse utilities (agent-centric API)
    elif name in ("detect_url_scheme", "is_path_like", "suggest_similar",
                  "is_policy_string", "parse_policy_string"):
        from .config import parse_utils
        result = getattr(parse_utils, name)
        _lazy_cache[name] = result
        return result
    
    # Context management config (already exists)
    elif name == "ManagerConfig":
        from .context.manager import ManagerConfig
        _lazy_cache[name] = ManagerConfig
        return ManagerConfig
    elif name == "ContextManager":
        from .context.manager import ContextManager
        _lazy_cache[name] = ContextManager
        return ContextManager
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
    'Agents',
    'Task',
    
    # Tool essentials
    'tool',
    'Tools',
    
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
# - Workflow, WorkflowStep, Route, Parallel, Loop, Repeat, Pipeline, etc.
# - MCP, FlowDisplay, track_workflow, FastContext, etc.
# - Plan, PlanStep, TodoList, PlanningAgent, ApprovalCallback, etc.
# - RAG, RAGConfig, RAGResult, AGUI, A2A, etc.
# - All telemetry, display, and utility functions
# ============================================================================
