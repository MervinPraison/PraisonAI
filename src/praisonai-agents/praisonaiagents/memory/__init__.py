"""
Memory module for PraisonAI Agents

This module provides memory management capabilities including:
- Short-term memory (STM) for ephemeral context
- Long-term memory (LTM) for persistent knowledge  
- Entity memory for structured data
- User memory for preferences/history
- Quality-based storage decisions
- Graph memory support via Mem0
- Session save/resume (like Gemini CLI)
- Context compression (like Gemini CLI)
- Checkpointing (like Gemini CLI)
- Rules management (like Cursor/Windsurf)
- Auto-generated memories (like Windsurf Cascade)
- Workflows (like Windsurf)
- Hooks (like Windsurf Cascade Hooks)
- Docs management (like Cursor docs)
- MCP config management (like Cursor .cursor/mcp/)

Protocols:
- MemoryProtocol: Minimal interface for memory implementations
- AsyncMemoryProtocol: Async interface for memory
- ResettableMemoryProtocol: Interface with reset methods

Memory Providers:
- FileMemory: Zero-dependency JSON file-based storage (default)
- Memory: Full-featured with SQLite, ChromaDB, Mem0, MongoDB support
- RulesManager: Rules/instructions file management
- AutoMemory: Automatic memory extraction from conversations
- WorkflowManager: Multi-step workflow execution
- HooksManager: Pre/post operation hooks
- DocsManager: Documentation context management
- MCPConfigManager: MCP server configuration management
"""

from .file_memory import FileMemory, create_memory
from .rules_manager import RulesManager, Rule, create_rules_manager
from .docs_manager import DocsManager, Doc
from .mcp_config import MCPConfigManager, MCPConfig
from .protocols import (
    MemoryProtocol, 
    AsyncMemoryProtocol, 
    ResettableMemoryProtocol,
    DeletableMemoryProtocol,
    AsyncDeletableMemoryProtocol,
    EntityMemoryProtocol,
)


# Lazy imports for optional modules to avoid dependency issues and improve startup time
def __getattr__(name):
    if name == "Memory":
        from .memory import Memory
        return Memory
    if name == "AutoMemory":
        from .auto_memory import AutoMemory
        return AutoMemory
    if name == "AutoMemoryExtractor":
        from .auto_memory import AutoMemoryExtractor
        return AutoMemoryExtractor
    if name == "create_auto_memory":
        from .auto_memory import create_auto_memory
        return create_auto_memory
    # Workflows - now in dedicated module, re-export for backward compatibility
    if name == "WorkflowManager":
        from ..workflows import WorkflowManager
        return WorkflowManager
    if name == "Workflow":
        from ..workflows import Workflow
        return Workflow
    if name == "Task":
        from ..workflows import Task
        return Task
    if name == "WorkflowContext":
        from ..workflows import WorkflowContext
        return WorkflowContext
    if name == "StepResult":
        from ..workflows import StepResult
        return StepResult
    if name == "Pipeline":
        from ..workflows import Pipeline
        return Pipeline
    if name == "Route":
        from ..workflows import Route
        return Route
    if name == "Parallel":
        from ..workflows import Parallel
        return Parallel
    if name == "Loop":
        from ..workflows import Loop
        return Loop
    if name == "Repeat":
        from ..workflows import Repeat
        return Repeat
    if name == "route":
        from ..workflows import route
        return route
    if name == "parallel":
        from ..workflows import parallel
        return parallel
    if name == "loop":
        from ..workflows import loop
        return loop
    if name == "repeat":
        from ..workflows import repeat
        return repeat
    # Backward compatibility aliases
    if name == "StepInput":
        from ..workflows import WorkflowContext
        return WorkflowContext
    if name == "StepOutput":
        from ..workflows import StepResult
        return StepResult
    if name == "create_workflow_manager":
        from ..workflows.workflows import create_workflow_manager
        return create_workflow_manager
    if name == "HooksManager":
        from .hooks import HooksManager
        return HooksManager
    if name == "HookResult":
        from .hooks import HookResult
        return HookResult
    if name == "create_hooks_manager":
        from .hooks import create_hooks_manager
        return create_hooks_manager
    # Learn module
    if name == "LearnManager":
        from .learn import LearnManager
        return LearnManager
    if name == "PersonaStore":
        from .learn import PersonaStore
        return PersonaStore
    if name == "InsightStore":
        from .learn import InsightStore
        return InsightStore
    if name == "ThreadStore":
        from .learn import ThreadStore
        return ThreadStore
    if name == "PatternStore":
        from .learn import PatternStore
        return PatternStore
    if name == "DecisionStore":
        from .learn import DecisionStore
        return DecisionStore
    if name == "FeedbackStore":
        from .learn import FeedbackStore
        return FeedbackStore
    if name == "ImprovementStore":
        from .learn import ImprovementStore
        return ImprovementStore
    # DocsManager and MCPConfigManager are already imported at module level
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    # Core memory
    "FileMemory", 
    "Memory", 
    "create_memory",
    # Rules management
    "RulesManager", 
    "Rule", 
    "create_rules_manager",
    # Auto memory
    "AutoMemory",
    "AutoMemoryExtractor",
    "create_auto_memory",
    # Workflows (re-exported from praisonaiagents.workflows for backward compatibility)
    "WorkflowManager",
    "Workflow",
    "Pipeline",
    "Task",
    "WorkflowContext",
    "StepResult",
    "create_workflow_manager",
    # Workflow patterns
    "Route",
    "Parallel",
    "Loop",
    "Repeat",
    "route",
    "parallel",
    "loop",
    "repeat",
    # Hooks
    "HooksManager",
    "HookResult",
    "create_hooks_manager",
    # Docs management
    "DocsManager",
    "Doc",
    # MCP config management
    "MCPConfigManager",
    "MCPConfig",
    # Learn module
    "LearnManager",
    "PersonaStore",
    "InsightStore",
    "ThreadStore",
    "PatternStore",
    "DecisionStore",
    "FeedbackStore",
    "ImprovementStore",
    # Protocols
    "MemoryProtocol",
    "AsyncMemoryProtocol",
    "ResettableMemoryProtocol",
    "DeletableMemoryProtocol",
    "AsyncDeletableMemoryProtocol",
    "EntityMemoryProtocol",
] 