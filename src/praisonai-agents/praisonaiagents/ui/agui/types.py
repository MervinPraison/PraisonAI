"""
AG-UI Protocol Types

This module defines the event types and message types for the AG-UI protocol,
following the ag-ui-protocol specification.
"""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """AG-UI Event Types."""
    TEXT_MESSAGE_START = "TEXT_MESSAGE_START"
    TEXT_MESSAGE_CONTENT = "TEXT_MESSAGE_CONTENT"
    TEXT_MESSAGE_END = "TEXT_MESSAGE_END"
    TOOL_CALL_START = "TOOL_CALL_START"
    TOOL_CALL_ARGS = "TOOL_CALL_ARGS"
    TOOL_CALL_END = "TOOL_CALL_END"
    TOOL_CALL_RESULT = "TOOL_CALL_RESULT"
    STATE_SNAPSHOT = "STATE_SNAPSHOT"
    STATE_DELTA = "STATE_DELTA"
    RUN_STARTED = "RUN_STARTED"
    RUN_FINISHED = "RUN_FINISHED"
    RUN_ERROR = "RUN_ERROR"
    STEP_STARTED = "STEP_STARTED"
    STEP_FINISHED = "STEP_FINISHED"
    CUSTOM = "CUSTOM"


class BaseEvent(BaseModel):
    """Base event for all AG-UI events."""
    type: EventType
    timestamp: Optional[int] = None
    
    model_config = {"use_enum_values": True}


# Text Message Events
class TextMessageStartEvent(BaseEvent):
    """Event indicating the start of a text message."""
    type: Literal["TEXT_MESSAGE_START"] = "TEXT_MESSAGE_START"
    message_id: str
    role: str = "assistant"


class TextMessageContentEvent(BaseEvent):
    """Event containing text message content."""
    type: Literal["TEXT_MESSAGE_CONTENT"] = "TEXT_MESSAGE_CONTENT"
    message_id: str
    delta: str


class TextMessageEndEvent(BaseEvent):
    """Event indicating the end of a text message."""
    type: Literal["TEXT_MESSAGE_END"] = "TEXT_MESSAGE_END"
    message_id: str


# Tool Call Events
class ToolCallStartEvent(BaseEvent):
    """Event indicating the start of a tool call."""
    type: Literal["TOOL_CALL_START"] = "TOOL_CALL_START"
    tool_call_id: str
    tool_call_name: str
    parent_message_id: Optional[str] = None


class ToolCallArgsEvent(BaseEvent):
    """Event containing tool call arguments."""
    type: Literal["TOOL_CALL_ARGS"] = "TOOL_CALL_ARGS"
    tool_call_id: str
    delta: str


class ToolCallEndEvent(BaseEvent):
    """Event indicating the end of a tool call."""
    type: Literal["TOOL_CALL_END"] = "TOOL_CALL_END"
    tool_call_id: str


class ToolCallResultEvent(BaseEvent):
    """Event containing tool call result."""
    type: Literal["TOOL_CALL_RESULT"] = "TOOL_CALL_RESULT"
    message_id: str
    tool_call_id: str
    content: str
    role: Optional[Literal["tool"]] = "tool"


# Run Lifecycle Events
class RunStartedEvent(BaseEvent):
    """Event indicating a run has started."""
    type: Literal["RUN_STARTED"] = "RUN_STARTED"
    thread_id: str
    run_id: str
    parent_run_id: Optional[str] = None


class RunFinishedEvent(BaseEvent):
    """Event indicating a run has finished."""
    type: Literal["RUN_FINISHED"] = "RUN_FINISHED"
    thread_id: str
    run_id: str
    result: Optional[Any] = None


class RunErrorEvent(BaseEvent):
    """Event indicating a run error."""
    type: Literal["RUN_ERROR"] = "RUN_ERROR"
    message: str
    code: Optional[str] = None


# Step Events
class StepStartedEvent(BaseEvent):
    """Event indicating a step has started."""
    type: Literal["STEP_STARTED"] = "STEP_STARTED"
    step_name: str


class StepFinishedEvent(BaseEvent):
    """Event indicating a step has finished."""
    type: Literal["STEP_FINISHED"] = "STEP_FINISHED"
    step_name: str


# State Events
class StateSnapshotEvent(BaseEvent):
    """Event containing a state snapshot."""
    type: Literal["STATE_SNAPSHOT"] = "STATE_SNAPSHOT"
    snapshot: Dict[str, Any]


# Message Types
class FunctionCall(BaseModel):
    """Function call in a tool call."""
    name: str
    arguments: str


class ToolCall(BaseModel):
    """Tool call in a message."""
    id: str
    function: FunctionCall
    type: str = "function"


class Message(BaseModel):
    """AG-UI Message type."""
    role: Literal["user", "assistant", "system", "tool"]
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


class RunAgentInput(BaseModel):
    """Input for running an agent."""
    thread_id: str
    run_id: Optional[str] = None
    messages: Optional[List[Message]] = Field(default_factory=list)
    state: Optional[Dict[str, Any]] = None
    forwarded_props: Optional[Dict[str, Any]] = None


# Union type for all events
Event = Union[
    TextMessageStartEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    ToolCallStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    StateSnapshotEvent,
    RunStartedEvent,
    RunFinishedEvent,
    RunErrorEvent,
    StepStartedEvent,
    StepFinishedEvent,
]
