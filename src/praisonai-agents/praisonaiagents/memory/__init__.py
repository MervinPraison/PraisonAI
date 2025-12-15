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

Memory Providers:
- FileMemory: Zero-dependency JSON file-based storage (default)
- Memory: Full-featured with SQLite, ChromaDB, Mem0, MongoDB support
- RulesManager: Rules/instructions file management
- AutoMemory: Automatic memory extraction from conversations
- WorkflowManager: Multi-step workflow execution
- HooksManager: Pre/post operation hooks
"""

from .file_memory import FileMemory, create_memory
from .rules_manager import RulesManager, Rule, create_rules_manager

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
    if name == "WorkflowManager":
        from .workflows import WorkflowManager
        return WorkflowManager
    if name == "Workflow":
        from .workflows import Workflow
        return Workflow
    if name == "WorkflowStep":
        from .workflows import WorkflowStep
        return WorkflowStep
    if name == "create_workflow_manager":
        from .workflows import create_workflow_manager
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
    # Workflows
    "WorkflowManager",
    "Workflow",
    "WorkflowStep",
    "create_workflow_manager",
    # Hooks
    "HooksManager",
    "HookResult",
    "create_hooks_manager",
] 