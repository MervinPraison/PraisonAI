"""
CLI Features Module for PraisonAI

This module contains modular CLI feature handlers that extend the base CLI functionality.
Each feature is implemented as a separate module for maintainability and testability.

Features:
- guardrail: Output validation using LLM guardrails
- metrics: Token usage and cost tracking
- image: Image processing with ImageAgent
- telemetry: Usage monitoring and analytics
- mcp: Model Context Protocol server integration
- fast_context: Codebase search capability
- knowledge: RAG/vector store management
- session: Session management for multi-turn conversations
- tools: Tool registry management
- handoff: Agent-to-agent delegation
- auto_memory: Automatic memory extraction
- todo: Todo list management
- router: Smart model selection
- flow_display: Visual workflow tracking
- workflow: YAML workflow management
- n8n: Export workflows to n8n visual editor
- external_agents: External AI CLI tool integrations (Claude, Gemini, Codex, Cursor)
- slash_commands: Interactive slash commands (/help, /cost, /plan, etc.)
- autonomy_mode: Autonomy levels (suggest, auto-edit, full-auto)
- cost_tracker: Real-time cost and token tracking
- message_queue: Message queuing while agent is processing
- at_mentions: @ mention autocomplete for files and directories
- compare: CLI command comparison feature
- eval: Agent evaluation framework (accuracy, performance, reliability, criteria)
- hooks: Hook system for intercepting and modifying agent behavior
- checkpoints: Shadow git checkpointing for file-level undo/restore
- background: Background agent task execution and management
- thinking: Thinking budget management
- compaction: Context compaction settings
- output_style: Output style configuration
- ollama: Ollama provider and Weak-Model-Proof execution
"""

# Type hints available for IDE support

# Lazy imports to avoid performance impact
__all__ = [
    'GuardrailHandler',
    'MetricsHandler', 
    'ImageHandler',
    'TelemetryHandler',
    'MCPHandler',
    'FastContextHandler',
    'KnowledgeHandler',
    'SessionHandler',
    'ToolsHandler',
    'HandoffHandler',
    'AutoMemoryHandler',
    'TodoHandler',
    'RouterHandler',
    'FlowDisplayHandler',
    'WorkflowHandler',
    'N8nHandler',
    'ExternalAgentsHandler',
    # New CLI enhancement features
    'SlashCommandHandler',
    'AutonomyModeHandler',
    'CostTrackerHandler',
    'RepoMapHandler',
    'InteractiveTUIHandler',
    'GitIntegrationHandler',
    'SandboxExecutorHandler',
    'MessageQueueHandler',
    # @ mention autocomplete
    'AtMentionCompleter',
    'CombinedCompleter',
    'FileSearchService',
    # Evaluation
    'EvalHandler',
    # Compare feature
    'CompareHandler',
    # Agent Skills
    'SkillsHandler',
    # Hooks
    'HooksHandler',
    # Checkpoints
    'CheckpointsHandler',
    # Background
    'BackgroundHandler',
    # Thinking, Compaction, Output Style
    'ThinkingHandler',
    'CompactionHandler',
    'OutputStyleHandler',
    # Ollama + WMP
    'OllamaHandler',
    # Capabilities (LiteLLM endpoint parity)
    'CapabilitiesHandler',
    # Performance benchmarking
    'PerformanceHandler',
    # Comprehensive benchmarking
    'BenchmarkHandler',
    # Lite agent (BYO-LLM)
    'LiteHandler',
    # Agent-centric tools (LSP/ACP powered)
    'create_agent_centric_tools',
    'InteractiveRuntime',
    'RuntimeConfig',
    'CodeIntelligenceRouter',
    'ActionOrchestrator',
    # Interactive tools provider (canonical source)
    'get_interactive_tools',
    'resolve_tool_groups',
    'ToolConfig',
    'TOOL_GROUPS',
]

def __getattr__(name):
    """Lazy load handlers to minimize import overhead."""
    if name == 'GuardrailHandler':
        from .guardrail import GuardrailHandler
        return GuardrailHandler
    elif name == 'MetricsHandler':
        from .metrics import MetricsHandler
        return MetricsHandler
    elif name == 'ImageHandler':
        from .image import ImageHandler
        return ImageHandler
    elif name == 'TelemetryHandler':
        from .telemetry import TelemetryHandler
        return TelemetryHandler
    elif name == 'MCPHandler':
        from .mcp import MCPHandler
        return MCPHandler
    elif name == 'FastContextHandler':
        from .fast_context import FastContextHandler
        return FastContextHandler
    elif name == 'KnowledgeHandler':
        from .knowledge import KnowledgeHandler
        return KnowledgeHandler
    elif name == 'SessionHandler':
        from .session import SessionHandler
        return SessionHandler
    elif name == 'ToolsHandler':
        from .tools import ToolsHandler
        return ToolsHandler
    elif name == 'HandoffHandler':
        from .handoff import HandoffHandler
        return HandoffHandler
    elif name == 'AutoMemoryHandler':
        from .auto_memory import AutoMemoryHandler
        return AutoMemoryHandler
    elif name == 'TodoHandler':
        from .todo import TodoHandler
        return TodoHandler
    elif name == 'RouterHandler':
        from .router import RouterHandler
        return RouterHandler
    elif name == 'FlowDisplayHandler':
        from .flow_display import FlowDisplayHandler
        return FlowDisplayHandler
    elif name == 'WorkflowHandler':
        from .workflow import WorkflowHandler
        return WorkflowHandler
    elif name == 'N8nHandler':
        from .n8n import N8nHandler
        return N8nHandler
    elif name == 'ExternalAgentsHandler':
        from .external_agents import ExternalAgentsHandler
        return ExternalAgentsHandler
    # New CLI enhancement features
    elif name == 'SlashCommandHandler':
        from .slash_commands import SlashCommandHandler
        return SlashCommandHandler
    elif name == 'AutonomyModeHandler':
        from .autonomy_mode import AutonomyModeHandler
        return AutonomyModeHandler
    elif name == 'CostTrackerHandler':
        from .cost_tracker import CostTrackerHandler
        return CostTrackerHandler
    elif name == 'RepoMapHandler':
        from .repo_map import RepoMapHandler
        return RepoMapHandler
    elif name == 'InteractiveTUIHandler':
        from .interactive_tui import InteractiveTUIHandler
        return InteractiveTUIHandler
    elif name == 'GitIntegrationHandler':
        from .git_integration import GitIntegrationHandler
        return GitIntegrationHandler
    elif name == 'SandboxExecutorHandler':
        from .sandbox_executor import SandboxExecutorHandler
        return SandboxExecutorHandler
    elif name == 'MessageQueueHandler':
        from .message_queue import MessageQueueHandler
        return MessageQueueHandler
    # @ mention autocomplete
    elif name == 'AtMentionCompleter':
        from .at_mentions import AtMentionCompleter
        return AtMentionCompleter
    elif name == 'CombinedCompleter':
        from .at_mentions import CombinedCompleter
        return CombinedCompleter
    elif name == 'FileSearchService':
        from .at_mentions import FileSearchService
        return FileSearchService
    elif name == 'CompareHandler':
        from .compare import CompareHandler
        return CompareHandler
    elif name == 'EvalHandler':
        from .eval import EvalHandler
        return EvalHandler
    elif name == 'SkillsHandler':
        from .skills import SkillsHandler
        return SkillsHandler
    elif name == 'HooksHandler':
        from .hooks import HooksHandler
        return HooksHandler
    elif name == 'CheckpointsHandler':
        from .checkpoints import CheckpointsHandler
        return CheckpointsHandler
    elif name == 'BackgroundHandler':
        from .background import BackgroundHandler
        return BackgroundHandler
    elif name == 'ThinkingHandler':
        from .thinking import ThinkingHandler
        return ThinkingHandler
    elif name == 'CompactionHandler':
        from .compaction import CompactionHandler
        return CompactionHandler
    elif name == 'OutputStyleHandler':
        from .output_style import OutputStyleHandler
        return OutputStyleHandler
    elif name == 'OllamaHandler':
        from .ollama import OllamaHandler
        return OllamaHandler
    elif name == 'CapabilitiesHandler':
        from .capabilities import CapabilitiesHandler
        return CapabilitiesHandler
    elif name == 'PerformanceHandler':
        from .performance import PerformanceHandler
        return PerformanceHandler
    elif name == 'BenchmarkHandler':
        from .benchmark import BenchmarkHandler
        return BenchmarkHandler
    elif name == 'LiteHandler':
        from .lite import LiteHandler
        return LiteHandler
    # Agent-centric tools (LSP/ACP powered)
    elif name == 'create_agent_centric_tools':
        from .agent_tools import create_agent_centric_tools
        return create_agent_centric_tools
    elif name == 'InteractiveRuntime':
        from .interactive_runtime import InteractiveRuntime
        return InteractiveRuntime
    elif name == 'RuntimeConfig':
        from .interactive_runtime import RuntimeConfig
        return RuntimeConfig
    elif name == 'CodeIntelligenceRouter':
        from .code_intelligence import CodeIntelligenceRouter
        return CodeIntelligenceRouter
    elif name == 'ActionOrchestrator':
        from .action_orchestrator import ActionOrchestrator
        return ActionOrchestrator
    # Interactive tools provider (canonical source)
    elif name == 'get_interactive_tools':
        from .interactive_tools import get_interactive_tools
        return get_interactive_tools
    elif name == 'resolve_tool_groups':
        from .interactive_tools import resolve_tool_groups
        return resolve_tool_groups
    elif name == 'ToolConfig':
        from .interactive_tools import ToolConfig
        return ToolConfig
    elif name == 'TOOL_GROUPS':
        from .interactive_tools import TOOL_GROUPS
        return TOOL_GROUPS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
