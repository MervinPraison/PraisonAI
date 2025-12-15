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
    from praisonaiagents import Agent, Task, PraisonAIAgents
    
    agents = PraisonAIAgents(
        agents=[agent1, agent2],
        tasks=[task1, task2],
        planning=True,           # Enable planning mode
        planning_llm="gpt-4o-mini"  # Optional: custom LLM
    )
    
    result = agents.start()
"""

from .plan import Plan, PlanStep
from .todo import TodoList, TodoItem
from .storage import PlanStorage
from .planner import PlanningAgent
from .approval import ApprovalCallback

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
