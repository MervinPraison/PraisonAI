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
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
