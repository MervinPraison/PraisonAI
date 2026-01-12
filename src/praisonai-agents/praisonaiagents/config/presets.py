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
    # Actions preset - opt-in observability
    # Shows action trace (tool calls, agent lifecycle) + final output
    # Registers callbacks, outputs to stderr
    "actions": {
        "verbose": False,
        "markdown": False,
        "stream": False,
        "metrics": False,
        "reasoning_steps": False,
        "actions_trace": True,  # Special flag for action trace mode
    },
    # Plain preset - final output only, no action trace
    "plain": {
        "verbose": False,
        "markdown": False,
        "stream": False,
        "metrics": False,
        "reasoning_steps": False,
        "actions_trace": False,
    },
    "minimal": {
        "verbose": False,
        "markdown": False,
        "stream": False,
        "metrics": False,
        "reasoning_steps": False,
    },
    "normal": {
        "verbose": True,
        "markdown": True,
        "stream": False,
        "metrics": False,
        "reasoning_steps": False,
    },
    "verbose": {
        "verbose": True,
        "markdown": True,
        "stream": False,
        "metrics": True,
        "reasoning_steps": True,
    },
    "debug": {
        "verbose": True,
        "markdown": True,
        "stream": False,
        "metrics": True,
        "reasoning_steps": True,
    },
    # Streaming preset - enables streaming by default
    "stream": {
        "verbose": True,
        "markdown": True,
        "stream": True,
        "metrics": False,
        "reasoning_steps": False,
    },
    # JSON preset - JSONL output for piping
    "json": {
        "verbose": False,
        "markdown": False,
        "stream": False,
        "metrics": False,
        "reasoning_steps": False,
        "actions_trace": True,
        "json_output": True,  # Output as JSONL
    },
}

# Default output mode - can be overridden by PRAISONAI_OUTPUT env var
# "silent" = zero overhead, fastest performance (DEFAULT)
# "actions" = tool call trace + final output (opt-in observability)
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
# Workflow Output Presets
# =============================================================================

WORKFLOW_OUTPUT_PRESETS: Dict[str, Dict[str, Any]] = {
    "silent": {"verbose": False, "stream": False},
    "minimal": {"verbose": False, "stream": True},
    "normal": {"verbose": False, "stream": True},
    "verbose": {"verbose": True, "stream": True},
    "debug": {"verbose": True, "stream": True},
}


# =============================================================================
# Knowledge Presets
# =============================================================================

KNOWLEDGE_PRESETS: Dict[str, Dict[str, Any]] = {
    "auto": {"auto_retrieve": True},
}
