"""
Tool Loop Detection for PraisonAI Agents.

Detects when an agent is stuck calling the same tool repeatedly with
identical arguments and no progress.

Inspired by OpenClaw's tool-loop-detection.ts (624 lines, 4 detectors).
Adapted to Python with PraisonAI's protocol-driven, zero-dep philosophy.

Zero Performance Impact:
- Disabled by default (enabled=False)
- Uses stdlib only: hashlib, json
- History is per-agent-instance (no global mutable state)

Usage:
    from praisonaiagents.agent.loop_detection import (
        LoopDetectionConfig, detect_tool_loop, record_tool_call, record_tool_outcome
    )
"""

from __future__ import annotations

import hashlib
import json
import logging
from praisonaiagents._logging import get_logger
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, TypedDict

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class LoopDetectionConfig:
    """
    Configuration for tool loop detection.

    Attributes:
        enabled: Whether loop detection is active. Default False (opt-in).
        history_size: Sliding window size for tool call history.
        warn_threshold: Number of identical (tool, args) calls before warning.
        critical_threshold: Number before critical/circuit-break. Must > warn.
        detectors: Which detectors are active.
    """
    enabled: bool = False
    history_size: int = 30
    warn_threshold: int = 10
    critical_threshold: int = 20
    detectors: Dict[str, bool] = field(default_factory=lambda: {
        "generic_repeat": True,
        "poll_no_progress": True,
        "ping_pong": True,
    })

    def __post_init__(self) -> None:
        # Auto-correct: critical must always be > warn
        if self.critical_threshold <= self.warn_threshold:
            self.critical_threshold = self.warn_threshold + 1

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

class LoopDetectionResult(TypedDict, total=False):
    stuck: bool
    level: Optional[Literal["warning", "critical"]]
    detector: Optional[str]
    message: Optional[str]
    count: int

_NOT_STUCK: LoopDetectionResult = {"stuck": False}

# ---------------------------------------------------------------------------
# History record
# ---------------------------------------------------------------------------

class ToolCallRecord(TypedDict, total=False):
    tool_name: str
    args_hash: str
    result_hash: Optional[str]
    timestamp: float

# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------

def _stable_json(value: Any) -> str:
    """Deterministic JSON serialization (sorted keys, str fallback)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return json.dumps(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_stable_json(v) for v in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value.keys())
        parts = [json.dumps(k) + ":" + _stable_json(value[k]) for k in keys]
        return "{" + ",".join(parts) + "}"
    # Fallback for non-serializable objects
    try:
        return json.dumps(str(value))
    except Exception:
        return '"<unserializable>"'

def _sha256_hex(text: str, prefix_len: int = 16) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:prefix_len]

def hash_tool_call(tool_name: str, args: Any) -> str:
    """
    Compute a stable hash for a (tool_name, args) pair.

    Args:
        tool_name: Name of the tool being called
        args: Arguments dict or any serializable value

    Returns:
        16-character hex string
    """
    stable = _stable_json({"t": tool_name, "a": args})
    return _sha256_hex(stable)

def _hash_result(result: Any) -> Optional[str]:
    """Hash a tool result for no-progress detection."""
    if result is None:
        return None
    try:
        stable = _stable_json(result)
        return _sha256_hex(stable)
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Record tool call / outcome
# ---------------------------------------------------------------------------

def record_tool_call(
    history: List[ToolCallRecord],
    tool_name: str,
    args: Any,
    config: Optional[LoopDetectionConfig] = None,
) -> None:
    """
    Append a tool call to the history (before execution).

    Args:
        history: Mutable list of ToolCallRecord
        tool_name: Tool being called
        args: Tool arguments
        config: Loop detection config (for history_size)
    """
    max_size = config.history_size if config else 30
    history.append(ToolCallRecord(
        tool_name=tool_name,
        args_hash=hash_tool_call(tool_name, args),
        result_hash=None,
        timestamp=time.time(),
    ))
    # Trim to sliding window
    if len(history) > max_size:
        del history[: len(history) - max_size]

def record_tool_outcome(
    history: List[ToolCallRecord],
    tool_name: str,
    args: Any,
    result: Any,
    config: Optional[LoopDetectionConfig] = None,
) -> None:
    """
    Update the most recent matching record with result hash (after execution).

    Args:
        history: Mutable list of ToolCallRecord
        tool_name: Tool that was called
        args: Arguments that were passed
        result: The return value of the tool
        config: Loop detection config
    """
    args_hash = hash_tool_call(tool_name, args)
    result_hash = _hash_result(result)
    if result_hash is None:
        return

    # Find the latest matching record without a result_hash
    for i in range(len(history) - 1, -1, -1):
        rec = history[i]
        if rec["tool_name"] == tool_name and rec["args_hash"] == args_hash and rec.get("result_hash") is None:
            history[i] = ToolCallRecord(
                tool_name=rec["tool_name"],
                args_hash=rec["args_hash"],
                result_hash=result_hash,
                timestamp=rec["timestamp"],
            )
            return

# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

def _known_poll_tool(tool_name: str) -> bool:
    """Heuristic: tools whose names suggest polling/waiting."""
    _poll_keywords = ("status", "poll", "check", "wait", "ping", "health", "command_status")
    name_lower = tool_name.lower()
    return any(kw in name_lower for kw in _poll_keywords)

def _count_generic_repeat(
    history: List[ToolCallRecord],
    args_hash: str,
    tool_name: str,
) -> int:
    """Count how many times this exact (tool, args) appears in history."""
    return sum(
        1 for rec in history
        if rec["tool_name"] == tool_name and rec["args_hash"] == args_hash
    )

def _no_progress_streak(
    history: List[ToolCallRecord],
    args_hash: str,
    tool_name: str,
) -> int:
    """
    Count consecutive tail records with identical (args_hash, result_hash).
    Returns 0 if any record has no result_hash or a different result_hash.
    """
    streak = 0
    first_result_hash: Optional[str] = None

    for rec in reversed(history):
        if rec["tool_name"] != tool_name or rec["args_hash"] != args_hash:
            continue
        rh = rec.get("result_hash")
        if rh is None:
            continue
        if first_result_hash is None:
            first_result_hash = rh
            streak = 1
        elif rh == first_result_hash:
            streak += 1
        else:
            break  # result changed — no longer a streak

    return streak

def _ping_pong_streak(
    history: List[ToolCallRecord],
    current_hash: str,
) -> int:
    """
    Detect alternating pattern: A, B, A, B, ...
    Returns count of consecutive alternating tail entries, 0 if not ping-pong.
    """
    if len(history) < 2:
        return 0

    last = history[-1]
    # Find the "other" hash in history (most recent != last)
    other_hash: Optional[str] = None
    for rec in reversed(history[:-1]):
        if rec["args_hash"] != last["args_hash"]:
            other_hash = rec["args_hash"]
            break

    if other_hash is None:
        return 0

    # Count tail alternation
    count = 0
    for i, rec in enumerate(reversed(history)):
        expected = last["args_hash"] if i % 2 == 0 else other_hash
        if rec["args_hash"] != expected:
            break
        count += 1

    # Current call must continue the ping-pong pattern
    if current_hash != (other_hash if count % 2 == 1 else last["args_hash"]):
        return 0

    return count + 1  # include current call

# ---------------------------------------------------------------------------
# Main detection function
# ---------------------------------------------------------------------------

def detect_tool_loop(
    history: List[ToolCallRecord],
    tool_name: str,
    args: Any,
    config: Optional[LoopDetectionConfig] = None,
) -> LoopDetectionResult:
    """
    Detect if agent is stuck in a tool call loop.

    Args:
        history: Mutable sliding window of ToolCallRecord
        tool_name: Tool being called now
        args: Arguments for this call
        config: Loop detection configuration

    Returns:
        LoopDetectionResult with stuck=False (safe) or stuck=True (warning/critical)
    """
    if config is None or not config.enabled:
        return _NOT_STUCK

    args_hash = hash_tool_call(tool_name, args)
    detectors = config.detectors or {}
    warn = config.warn_threshold
    critical = config.critical_threshold

    # --- poll_no_progress detector ---
    if detectors.get("poll_no_progress", True) and _known_poll_tool(tool_name):
        streak = _no_progress_streak(history, args_hash, tool_name)
        if streak >= critical:
            msg = (
                f"CRITICAL: '{tool_name}' called {streak} times with identical args "
                f"and identical result. Detected stuck polling loop. Stop and report failure."
            )
            logger.error(f"[loop_detection] {msg}")
            return LoopDetectionResult(
                stuck=True, level="critical",
                detector="poll_no_progress", message=msg, count=streak,
            )
        if streak >= warn:
            msg = (
                f"WARNING: '{tool_name}' has returned identical results {streak} times. "
                f"This looks like a stuck poll. Increase wait time or report failure."
            )
            logger.warning(f"[loop_detection] {msg}")
            return LoopDetectionResult(
                stuck=True, level="warning",
                detector="poll_no_progress", message=msg, count=streak,
            )

    # --- ping_pong detector ---
    if detectors.get("ping_pong", True):
        pp_count = _ping_pong_streak(history, args_hash)
        if pp_count >= critical:
            msg = (
                f"CRITICAL: Ping-pong loop detected ({pp_count} alternating calls). "
                f"Agent is oscillating between two tool states. Stop and report failure."
            )
            logger.error(f"[loop_detection] {msg}")
            return LoopDetectionResult(
                stuck=True, level="critical",
                detector="ping_pong", message=msg, count=pp_count,
            )
        if pp_count >= warn:
            msg = (
                f"WARNING: Alternating tool pattern detected ({pp_count} calls). "
                f"Stop ping-pong and try a different approach."
            )
            logger.warning(f"[loop_detection] {msg}")
            return LoopDetectionResult(
                stuck=True, level="warning",
                detector="ping_pong", message=msg, count=pp_count,
            )

    # --- generic_repeat detector ---
    if detectors.get("generic_repeat", True) and not _known_poll_tool(tool_name):
        count = _count_generic_repeat(history, args_hash, tool_name)
        if count >= critical:
            msg = (
                f"CRITICAL: '{tool_name}' called {count} times with identical args. "
                f"Agent is stuck. Execution blocked."
            )
            logger.error(f"[loop_detection] {msg}")
            return LoopDetectionResult(
                stuck=True, level="critical",
                detector="generic_repeat", message=msg, count=count,
            )
        if count >= warn:
            msg = (
                f"WARNING: '{tool_name}' called {count} times with identical args. "
                f"If not making progress, stop and report failure."
            )
            logger.warning(f"[loop_detection] {msg}")
            return LoopDetectionResult(
                stuck=True, level="warning",
                detector="generic_repeat", message=msg, count=count,
            )

    return _NOT_STUCK
