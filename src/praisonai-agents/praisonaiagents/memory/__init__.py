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

Memory Providers:
- FileMemory: Zero-dependency JSON file-based storage (default)
- Memory: Full-featured with SQLite, ChromaDB, Mem0, MongoDB support
- RulesManager: Rules/instructions file management
"""

from .file_memory import FileMemory, create_memory
from .rules_manager import RulesManager, Rule, create_rules_manager

# Lazy import for Memory to avoid dependency issues
def __getattr__(name):
    if name == "Memory":
        from .memory import Memory
        return Memory
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["FileMemory", "Memory", "create_memory", "RulesManager", "Rule", "create_rules_manager"] 