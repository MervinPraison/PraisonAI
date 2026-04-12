"""
Provider-agnostic event types for Managed Agent backends.

These dataclasses mirror the event types used by Anthropic's Managed Agents API
but are provider-agnostic. Any managed backend (Anthropic, local, OpenAI, etc.)
emits these events during execution.

All classes are lightweight dataclasses — no heavy dependencies.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class EventType(str, Enum):
    """Standard event types for managed agent sessions."""

    AGENT_MESSAGE = "agent.message"
    AGENT_TOOL_USE = "agent.tool_use"
    AGENT_CUSTOM_TOOL_USE = "agent.custom_tool_use"
    TOOL_CONFIRMATION = "agent.tool_confirmation"
    SESSION_IDLE = "session.status_idle"
    SESSION_RUNNING = "session.status_running"
    SESSION_ERROR = "session.error"
    USAGE = "session.usage"


class StopReason(str, Enum):
    """Why a session went idle."""

    END_TURN = "end_turn"
    REQUIRES_ACTION = "requires_action"
    MAX_TURNS = "max_turns"
    INTERRUPTED = "interrupted"
    ERROR = "error"


@dataclass
class ManagedEvent:
    """Base event emitted by a managed agent backend.

    Attributes:
        type: Event type string (e.g. ``"agent.message"``).
        timestamp: Unix timestamp when the event was created.
        metadata: Arbitrary provider-specific metadata.
    """

    type: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentMessageEvent(ManagedEvent):
    """Text content produced by the agent.

    Attributes:
        content: List of content blocks, each a dict with at least
            ``{"type": "text", "text": "..."}``.
    """

    content: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        if not self.type:
            self.type = EventType.AGENT_MESSAGE.value

    @property
    def text(self) -> str:
        """Convenience: concatenate all text blocks."""
        parts = []
        for block in self.content:
            t = block.get("text")
            if t:
                parts.append(t)
        return "".join(parts)


@dataclass
class ToolUseEvent(ManagedEvent):
    """Built-in tool invocation by the agent.

    Attributes:
        name: Tool name (e.g. ``"bash"``, ``"read"``, ``"write"``).
        input: Tool input parameters.
        tool_use_id: Unique ID for this tool invocation.
        needs_confirmation: Whether the tool requires user confirmation.
    """

    name: str = ""
    input: Dict[str, Any] = field(default_factory=dict)
    tool_use_id: str = ""
    needs_confirmation: bool = False

    def __post_init__(self):
        if not self.type:
            self.type = EventType.AGENT_TOOL_USE.value


@dataclass
class CustomToolUseEvent(ManagedEvent):
    """Custom (user-defined) tool invocation by the agent.

    Attributes:
        name: Custom tool name.
        input: Tool input parameters.
        tool_use_id: Unique ID for this tool invocation.
    """

    name: str = ""
    input: Dict[str, Any] = field(default_factory=dict)
    tool_use_id: str = ""

    def __post_init__(self):
        if not self.type:
            self.type = EventType.AGENT_CUSTOM_TOOL_USE.value


@dataclass
class ToolConfirmationEvent(ManagedEvent):
    """Tool requires user confirmation before execution.

    Attributes:
        name: Tool name requiring confirmation.
        input: Tool input parameters.
        tool_use_id: Unique ID for this tool invocation.
    """

    name: str = ""
    input: Dict[str, Any] = field(default_factory=dict)
    tool_use_id: str = ""

    def __post_init__(self):
        if not self.type:
            self.type = EventType.TOOL_CONFIRMATION.value


@dataclass
class SessionIdleEvent(ManagedEvent):
    """Session has gone idle (turn complete or action required).

    Attributes:
        stop_reason: Why the session stopped (see ``StopReason``).
        event_ids: Blocking event IDs if stop_reason is ``requires_action``.
    """

    stop_reason: str = StopReason.END_TURN.value
    event_ids: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.type:
            self.type = EventType.SESSION_IDLE.value


@dataclass
class SessionRunningEvent(ManagedEvent):
    """Session has transitioned to running state."""

    def __post_init__(self):
        if not self.type:
            self.type = EventType.SESSION_RUNNING.value


@dataclass
class SessionErrorEvent(ManagedEvent):
    """Session encountered an error.

    Attributes:
        error_message: Human-readable error description.
        error_code: Machine-readable error code (optional).
    """

    error_message: str = ""
    error_code: str = ""

    def __post_init__(self):
        if not self.type:
            self.type = EventType.SESSION_ERROR.value


@dataclass
class UsageEvent(ManagedEvent):
    """Token usage update.

    Attributes:
        input_tokens: Number of input tokens consumed.
        output_tokens: Number of output tokens generated.
        cache_creation_input_tokens: Tokens used for cache creation.
        cache_read_input_tokens: Tokens read from cache.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    def __post_init__(self):
        if not self.type:
            self.type = EventType.USAGE.value
