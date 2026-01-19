"""
Preset Registries for Consolidated Parameters.

Centralized preset definitions for all consolidated parameters.
These are used by the unified resolver for string preset lookups.

All presets are defined as dicts to avoid circular imports.
The resolver converts them to config instances as needed.
"""

from typing import Any, Dict


# =============================================================================
# Memory Presets
# =============================================================================

MEMORY_PRESETS: Dict[str, Dict[str, Any]] = {
    "file": {"backend": "file"},
    "sqlite": {"backend": "sqlite"},
    "redis": {"backend": "redis"},
    "postgres": {"backend": "postgres"},
    "postgresql": {"backend": "postgres"},
    "mem0": {"backend": "mem0"},
    "mongodb": {"backend": "mongodb"},
}

MEMORY_URL_SCHEMES: Dict[str, str] = {
    "postgresql": "postgres",
    "postgres": "postgres",
    "redis": "redis",
    "rediss": "redis",  # Redis with SSL
    "sqlite": "sqlite",
    "mongodb": "mongodb",
    "mongodb+srv": "mongodb",
}


# =============================================================================
# Output Presets
# =============================================================================
# 
# Preset Hierarchy (from least to most output):
#   silent  → Nothing (default for SDK, max performance)
#   text    → Response only, simple format
#   verbose → Task + Tools inline + Response panel
#   debug   → verbose + metrics footer (tokens, cost, model)
#   stream  → Real-time token streaming
#   json    → Machine-readable JSONL events
#
# =============================================================================

OUTPUT_PRESETS: Dict[str, Dict[str, Any]] = {
    # Silent preset - DEFAULT for SDK
    # Zero overhead, no callbacks, no I/O on hot path
    # Fastest performance for programmatic use
    "silent": {
        "verbose": False,
        "markdown": False,
        "stream": False,
        "metrics": False,
        "reasoning_steps": False,
        "actions_trace": False,
    },
    # Status preset - Shows tool calls and response without timestamps
    # Simple progress indicator: ▸ tool → result ✓
    "status": {
        "verbose": False,
        "markdown": False,
        "stream": False,
        "metrics": False,
        "reasoning_steps": False,
        "actions_trace": True,
        "simple_output": True,  # Simple format without timestamps
    },
    # Trace preset - Full execution trace with timestamps
    # Shows: [HH:MM:SS] ▸ tool → result [0.2s] ✓
    # Ideal for debugging and monitoring
    "trace": {
        "verbose": False,
        "markdown": False,
        "stream": False,
        "metrics": False,
        "reasoning_steps": False,
        "actions_trace": True,
        "status_trace": True,  # Enable timestamped status output
    },
    # Verbose preset - Full interactive output with panels
    # Shows: Task prompt, Tool calls (inline), Response panel
    # Best for interactive terminal use
    "verbose": {
        "verbose": True,
        "markdown": True,
        "stream": False,
        "metrics": False,
        "reasoning_steps": False,
    },
    # Debug preset - trace + metrics (NO boxes)
    # Shows: [timestamp] tool calls, metrics footer, reasoning steps
    # Best for developers debugging agent behavior
    "debug": {
        "verbose": False,  # No boxes
        "markdown": False,
        "stream": False,
        "metrics": True,  # Shows metrics footer
        "reasoning_steps": True,
        "actions_trace": True,
        "status_trace": True,  # Timestamps like trace
        "show_parameters": True,
    },
    # Streaming preset - enables streaming by default
    "stream": {
        "verbose": True,
        "markdown": True,
        "stream": True,
        "metrics": False,
        "reasoning_steps": False,
    },
    # JSON preset - JSONL output for piping/scripting
    "json": {
        "verbose": False,
        "markdown": False,
        "stream": False,
        "metrics": False,
        "reasoning_steps": False,
        "actions_trace": True,
        "json_output": True,  # Output as JSONL
    },
    
    # ==========================================================================
    # ALIASES (for backward compatibility)
    # ==========================================================================
    # plain → silent (identical behavior)
    "plain": {
        "verbose": False,
        "markdown": False,
        "stream": False,
        "metrics": False,
        "reasoning_steps": False,
        "actions_trace": False,
    },
    # minimal → silent (identical behavior)
    "minimal": {
        "verbose": False,
        "markdown": False,
        "stream": False,
        "metrics": False,
        "reasoning_steps": False,
    },
    # normal → verbose (consolidated)
    "normal": {
        "verbose": True,
        "markdown": True,
        "stream": False,
        "metrics": False,
        "reasoning_steps": False,
    },
    # actions → status (renamed for clarity)
    "actions": {
        "verbose": False,
        "markdown": False,
        "stream": False,
        "metrics": False,
        "reasoning_steps": False,
        "actions_trace": True,
        "simple_output": True,
    },
    # text → status (old name, kept for backward compat)
    "text": {
        "verbose": False,
        "markdown": False,
        "stream": False,
        "metrics": False,
        "reasoning_steps": False,
        "actions_trace": True,
        "simple_output": True,
    },
}

# Default output mode - can be overridden by PRAISONAI_OUTPUT env var
# "silent" = zero overhead, fastest performance (DEFAULT)
# "verbose" = full interactive display
# "debug" = verbose + metrics
DEFAULT_OUTPUT_MODE = "silent"


# =============================================================================
# Execution Presets
# =============================================================================

EXECUTION_PRESETS: Dict[str, Dict[str, Any]] = {
    "fast": {
        "max_iter": 10,
        "max_retry_limit": 1,
        "max_rpm": None,
        "max_execution_time": None,
    },
    "balanced": {
        "max_iter": 20,
        "max_retry_limit": 2,
        "max_rpm": None,
        "max_execution_time": None,
    },
    "thorough": {
        "max_iter": 50,
        "max_retry_limit": 5,
        "max_rpm": None,
        "max_execution_time": None,
    },
    "unlimited": {
        "max_iter": 1000,
        "max_retry_limit": 10,
        "max_rpm": None,
        "max_execution_time": None,
    },
}


# =============================================================================
# Web Presets
# =============================================================================

WEB_PRESETS: Dict[str, Dict[str, Any]] = {
    # Providers
    "duckduckgo": {"search": True, "fetch": True, "search_provider": "duckduckgo"},
    "tavily": {"search": True, "fetch": True, "search_provider": "tavily"},
    "google": {"search": True, "fetch": True, "search_provider": "google"},
    "bing": {"search": True, "fetch": True, "search_provider": "bing"},
    "serper": {"search": True, "fetch": True, "search_provider": "serper"},
    # Modes
    "search_only": {"search": True, "fetch": False},
    "fetch_only": {"search": False, "fetch": True},
}


# =============================================================================
# Planning Presets
# =============================================================================

PLANNING_PRESETS: Dict[str, Dict[str, Any]] = {
    "reasoning": {"reasoning": True, "auto_approve": False, "read_only": False},
    "read_only": {"reasoning": False, "auto_approve": False, "read_only": True},
    "auto": {"reasoning": False, "auto_approve": True, "read_only": False},
}


# =============================================================================
# Reflection Presets
# =============================================================================

REFLECTION_PRESETS: Dict[str, Dict[str, Any]] = {
    "minimal": {"min_iterations": 1, "max_iterations": 1},
    "standard": {"min_iterations": 1, "max_iterations": 3},
    "thorough": {"min_iterations": 2, "max_iterations": 5},
}


# =============================================================================
# Guardrail Presets
# =============================================================================

GUARDRAIL_PRESETS: Dict[str, Dict[str, Any]] = {
    "strict": {"max_retries": 5, "on_fail": "raise"},
    "permissive": {"max_retries": 1, "on_fail": "skip"},
    "safety": {"max_retries": 3, "on_fail": "retry"},
}


# =============================================================================
# Context Presets
# =============================================================================

CONTEXT_PRESETS: Dict[str, Dict[str, Any]] = {
    "sliding_window": {"strategy": "sliding_window"},
    "summarize": {"strategy": "summarize"},
    "truncate": {"strategy": "truncate"},
}


# =============================================================================
# Autonomy Presets
# =============================================================================

AUTONOMY_PRESETS: Dict[str, Dict[str, Any]] = {
    "suggest": {"mode": "suggest"},
    "auto_edit": {"mode": "auto_edit"},
    "full_auto": {"mode": "full_auto"},
}


# =============================================================================
# Caching Presets
# =============================================================================

CACHING_PRESETS: Dict[str, Dict[str, Any]] = {
    "enabled": {"enabled": True, "prompt_caching": None},
    "disabled": {"enabled": False, "prompt_caching": None},
    "prompt": {"enabled": True, "prompt_caching": True},
}


# =============================================================================
# Multi-Agent Output Presets
# =============================================================================

MULTI_AGENT_OUTPUT_PRESETS: Dict[str, Dict[str, Any]] = {
    "verbose": {"verbose": 2, "stream": True},
    "minimal": {"verbose": 1, "stream": True},
    "silent": {"verbose": 0, "stream": False},
}


# =============================================================================
# Multi-Agent Execution Presets
# =============================================================================

MULTI_AGENT_EXECUTION_PRESETS: Dict[str, Dict[str, Any]] = {
    "fast": {"max_iter": 5, "max_retries": 2},
    "balanced": {"max_iter": 10, "max_retries": 5},
    "thorough": {"max_iter": 20, "max_retries": 5},
    "unlimited": {"max_iter": 100, "max_retries": 10},
}


# =============================================================================
# Workflow Step Execution Presets
# =============================================================================

WORKFLOW_STEP_EXECUTION_PRESETS: Dict[str, Dict[str, Any]] = {
    "fast": {"max_retries": 1, "quality_check": False},
    "balanced": {"max_retries": 3, "quality_check": True},
    "thorough": {"max_retries": 5, "quality_check": True},
}


# =============================================================================
# Workflow Output Presets - DEPRECATED, use OUTPUT_PRESETS instead (DRY)
# =============================================================================
# Workflows now use the same OUTPUT_PRESETS as Agent for consistency.
# This alias is kept for backward compatibility only.
WORKFLOW_OUTPUT_PRESETS = OUTPUT_PRESETS


# =============================================================================
# Knowledge Presets
# =============================================================================

KNOWLEDGE_PRESETS: Dict[str, Dict[str, Any]] = {
    "auto": {"auto_retrieve": True},
}
