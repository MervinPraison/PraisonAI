"""
Tool Loop Detection Plugin for PraisonAI Agents.

Registers a BEFORE_TOOL hook that detects repetitive tool call patterns
and blocks the agent when stuck in a loop.

Inspired by OpenClaw's tool-loop-detection.ts (624 lines, 4 detectors).

Usage:
    # Import to auto-register the hook globally
    import praisonaiagents.plugins.loop_detection_plugin

    # Or use with an agent via explicit hook registration
    from praisonaiagents import Agent
    from praisonaiagents.hooks.registry import get_default_registry
    from praisonaiagents.hooks.types import HookEvent

Zero Performance Impact:
    - Only active when this module is imported
    - Uses stdlib only (hashlib, json)
    - Disabled in production unless explicitly imported
"""

from __future__ import annotations

import logging
from praisonaiagents._logging import get_logger
import threading
from typing import List

from praisonaiagents.hooks.registry import add_hook
from praisonaiagents.hooks.types import HookEvent, HookInput, HookResult

from praisonaiagents.agent.loop_detection import (
    LoopDetectionConfig,
    LoopDetectionResult,
    detect_tool_loop,
    record_tool_call,
    ToolCallRecord,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Default configuration (can be overridden before import)
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = LoopDetectionConfig(
    enabled=True,
    history_size=30,
    warn_threshold=10,
    critical_threshold=20,
)

# ---------------------------------------------------------------------------
# Per-thread history (avoids shared mutable state across agents/threads)
# ---------------------------------------------------------------------------

_thread_local = threading.local()

def _get_history() -> List[ToolCallRecord]:
    """Get the thread-local tool call history."""
    if not hasattr(_thread_local, "history"):
        _thread_local.history = []
    return _thread_local.history

def reset_history() -> None:
    """Reset the tool call history for the current thread. Useful in tests."""
    _thread_local.history = []

# ---------------------------------------------------------------------------
# Hook implementation
# ---------------------------------------------------------------------------

def _loop_detection_hook(event: HookInput) -> HookResult:
    """
    BEFORE_TOOL hook: detect if agent is stuck in a tool call loop.

    Returns:
        - HookResult.allow() if not stuck (or below warning threshold)
        - HookResult.allow(reason=warning_msg) if at warning threshold
        - HookResult.block(reason=critical_msg) if at critical threshold
    """
    # BeforeToolInput has tool_name and tool_input fields.
    # Fall back to event.extra for compatibility with custom callers.
    tool_name: str = (
        getattr(event, "tool_name", None)
        or event.extra.get("tool_name", "")
    )
    tool_args = (
        getattr(event, "tool_input", None)
        or event.extra.get("tool_args", {})
        or {}
    )

    history = _get_history()

    # Check before recording
    result: LoopDetectionResult = detect_tool_loop(history, tool_name, tool_args, DEFAULT_CONFIG)

    # Record the call (after detection to count existing history)
    record_tool_call(history, tool_name, tool_args, DEFAULT_CONFIG)

    if not result.get("stuck"):
        return HookResult.allow()

    level = result.get("level")
    message = result.get("message", "Tool loop detected")
    count = result.get("count", 0)
    detector = result.get("detector", "unknown")

    if level == "critical":
        logger.error(
            f"[loop_detection_plugin] BLOCKED: {detector} detector, "
            f"tool={tool_name!r}, count={count}"
        )
        return HookResult.block(message)

    # Warning: allow but annotate (agent can see the warning in hook output)
    logger.warning(
        f"[loop_detection_plugin] WARNING: {detector} detector, "
        f"tool={tool_name!r}, count={count}"
    )
    # Return allow with additional_context so the runner can pass it back
    return HookResult(decision="allow", reason=message)

# ---------------------------------------------------------------------------
# Register hook on import (side effect is intentional for plugin pattern)
# ---------------------------------------------------------------------------

_hook_id = add_hook(HookEvent.BEFORE_TOOL, _loop_detection_hook)
logger.debug(f"[loop_detection_plugin] Registered BEFORE_TOOL hook: {_hook_id}")
