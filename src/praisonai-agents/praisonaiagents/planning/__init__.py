"""
Planning Module for PraisonAI Agents.

Provides Planning Mode functionality similar to:
- Cursor Plan Mode
- Windsurf Planning Mode  
- Claude Code Plan Mode
- Gemini CLI Plan Mode
- Codex CLI /plan command

Features:
- PlanningAgent for creating implementation plans
- Plan and PlanStep dataclasses for plan structure
- TodoList for tracking progress
- PlanStorage for persistence
- ApprovalCallback for plan approval flow
- Read-only mode for safe research

Usage:
    from praisonaiagents import Agent, Task, AgentManager
    
    agents = AgentManager(
        agents=[agent1, agent2],
        tasks=[task1, task2],
        planning=True,           # Enable planning mode
        planning_llm="gpt-4o-mini"  # Optional: custom LLM
    )
    
    result = agents.start()

This module uses lazy loading to minimize import time.
"""

# Module-level cache for lazy-loaded classes
_lazy_cache = {}

# Read-only tools that are allowed in plan mode
READ_ONLY_TOOLS = [
    "read_file",
    "list_directory",
    "search_codebase",
    "search_files",
    "grep_search",
    "find_files",
    "web_search",
    "get_file_content",
    "list_files",
    "read_document",
    "search_web",
    "fetch_url",
    "get_context",
]

# Restricted tools that are blocked in plan mode
RESTRICTED_TOOLS = [
    "write_file",
    "create_file",
    "delete_file",
    "execute_command",
    "run_command",
    "shell_command",
    "modify_file",
    "edit_file",
    "remove_file",
    "move_file",
    "copy_file",
    "mkdir",
    "rmdir",
    "git_commit",
    "git_push",
    "npm_install",
    "pip_install",
]

# Research tools that are safe for planning research
RESEARCH_TOOLS = [
    "web_search",
    "search_web",
    "duckduckgo_search",
    "tavily_search",
    "brave_search",
    "google_search",
    "read_url",
    "fetch_url",
    "read_file",
    "list_directory",
    "search_codebase",
    "grep_search",
    "find_files",
]


def __getattr__(name):
    """Lazy load planning classes to avoid importing heavy dependencies at module load time."""
    if name in _lazy_cache:
        return _lazy_cache[name]
    
    if name == "Plan":
        from .plan import Plan
        _lazy_cache[name] = Plan
        return Plan
    elif name == "PlanStep":
        from .plan import PlanStep
        _lazy_cache[name] = PlanStep
        return PlanStep
    elif name == "TodoList":
        from .todo import TodoList
        _lazy_cache[name] = TodoList
        return TodoList
    elif name == "TodoItem":
        from .todo import TodoItem
        _lazy_cache[name] = TodoItem
        return TodoItem
    elif name == "PlanStorage":
        from .storage import PlanStorage
        _lazy_cache[name] = PlanStorage
        return PlanStorage
    elif name == "PlanningAgent":
        from .planner import PlanningAgent
        _lazy_cache[name] = PlanningAgent
        return PlanningAgent
    elif name == "ApprovalCallback":
        from .approval import ApprovalCallback
        _lazy_cache[name] = ApprovalCallback
        return ApprovalCallback
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Plan",
    "PlanStep",
    "TodoList",
    "TodoItem",
    "PlanStorage",
    "PlanningAgent",
    "ApprovalCallback",
    "READ_ONLY_TOOLS",
    "RESTRICTED_TOOLS",
    "RESEARCH_TOOLS",
]
