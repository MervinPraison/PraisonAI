"""
AG-UI Event Streaming

Provides utilities for streaming PraisonAI agent responses as AG-UI events.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Set

from praisonaiagents.ui.agui.types import (
    BaseEvent,
    CustomEvent,
    TextMessageStartEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    ToolCallStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    RunStartedEvent,
    RunFinishedEvent,
    RunErrorEvent,
    StepStartedEvent,
    StepFinishedEvent,
    StateSnapshotEvent,
)
from praisonaiagents.ui.protocols import A2UI_MIME_TYPE


@dataclass
class EventBuffer:
    """Buffer to manage event ordering constraints."""
    
    active_tool_call_ids: Set[str] = field(default_factory=set)
    ended_tool_call_ids: Set[str] = field(default_factory=set)
    current_text_message_id: str = ""
    next_text_message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    pending_tool_calls_parent_id: str = ""
    
    def start_tool_call(self, tool_call_id: str) -> None:
        """Start a new tool call."""
        self.active_tool_call_ids.add(tool_call_id)
    
    def end_tool_call(self, tool_call_id: str) -> None:
        """End a tool call."""
        self.active_tool_call_ids.discard(tool_call_id)
        self.ended_tool_call_ids.add(tool_call_id)
    
    def start_text_message(self) -> str:
        """Start a new text message and return its ID."""
        self.current_text_message_id = self.next_text_message_id
        self.next_text_message_id = str(uuid.uuid4())
        return self.current_text_message_id
    
    def get_parent_message_id_for_tool_call(self) -> str:
        """Get the message ID to use as parent for tool calls."""
        if self.pending_tool_calls_parent_id:
            return self.pending_tool_calls_parent_id
        return self.current_text_message_id


# Event Creation Functions

def create_text_message_events(
    content: str,
    message_id: Optional[str] = None,
    role: str = "assistant"
) -> Iterator[BaseEvent]:
    """
    Create text message events for a complete message.
    
    Args:
        content: The message content
        message_id: Optional message ID (generated if not provided)
        role: Message role (default: assistant)
        
    Yields:
        TextMessageStartEvent, TextMessageContentEvent(s), TextMessageEndEvent
    """
    msg_id = message_id or str(uuid.uuid4())
    
    yield TextMessageStartEvent(message_id=msg_id, role=role)
    
    if content:
        yield TextMessageContentEvent(message_id=msg_id, delta=content)
    
    yield TextMessageEndEvent(message_id=msg_id)


def stream_text_chunks(
    chunks: Iterator[str],
    message_id: Optional[str] = None,
    role: str = "assistant"
) -> Iterator[BaseEvent]:
    """
    Stream text chunks as AG-UI events.
    
    Args:
        chunks: Iterator of text chunks
        message_id: Optional message ID
        role: Message role
        
    Yields:
        AG-UI events for the text stream
    """
    msg_id = message_id or str(uuid.uuid4())
    
    yield TextMessageStartEvent(message_id=msg_id, role=role)
    
    for chunk in chunks:
        if chunk:
            yield TextMessageContentEvent(message_id=msg_id, delta=chunk)
    
    yield TextMessageEndEvent(message_id=msg_id)


def create_tool_call_events(
    tool_call_id: str,
    tool_name: str,
    arguments: str,
    parent_message_id: Optional[str] = None
) -> Iterator[BaseEvent]:
    """
    Create tool call events.
    
    Args:
        tool_call_id: Unique ID for the tool call
        tool_name: Name of the tool being called
        arguments: JSON string of arguments
        parent_message_id: Optional parent message ID
        
    Yields:
        ToolCallStartEvent, ToolCallArgsEvent, ToolCallEndEvent
    """
    yield ToolCallStartEvent(
        tool_call_id=tool_call_id,
        tool_call_name=tool_name,
        parent_message_id=parent_message_id
    )
    
    yield ToolCallArgsEvent(
        tool_call_id=tool_call_id,
        delta=arguments
    )
    
    yield ToolCallEndEvent(tool_call_id=tool_call_id)


def create_tool_result_event(
    tool_call_id: str,
    content: str,
    message_id: Optional[str] = None
) -> ToolCallResultEvent:
    """
    Create a tool result event.
    
    Args:
        tool_call_id: ID of the tool call this is a result for
        content: Result content
        message_id: Optional message ID
        
    Returns:
        ToolCallResultEvent
    """
    return ToolCallResultEvent(
        message_id=message_id or str(uuid.uuid4()),
        tool_call_id=tool_call_id,
        content=content
    )


# Run Lifecycle Events

def create_run_started_event(thread_id: str, run_id: str) -> RunStartedEvent:
    """Create a run started event."""
    return RunStartedEvent(thread_id=thread_id, run_id=run_id)


def create_run_finished_event(
    thread_id: str,
    run_id: str,
    result: Optional[Any] = None
) -> RunFinishedEvent:
    """Create a run finished event."""
    return RunFinishedEvent(thread_id=thread_id, run_id=run_id, result=result)


def create_run_error_event(
    message: str,
    code: Optional[str] = None
) -> RunErrorEvent:
    """Create a run error event."""
    return RunErrorEvent(message=message, code=code)


# Step Events

def create_step_started_event(step_name: str) -> StepStartedEvent:
    """Create a step started event."""
    return StepStartedEvent(step_name=step_name)


def create_step_finished_event(step_name: str) -> StepFinishedEvent:
    """Create a step finished event."""
    return StepFinishedEvent(step_name=step_name)


# State Events

def create_state_snapshot_event(state: Dict[str, Any]) -> StateSnapshotEvent:
    """Create a state snapshot event."""
    return StateSnapshotEvent(snapshot=state)


# Async Streaming

async def async_stream_response(
    response_stream: AsyncIterator[str],
    thread_id: str,
    run_id: str
) -> AsyncIterator[BaseEvent]:
    """
    Stream an async response as AG-UI events.
    
    Args:
        response_stream: Async iterator of response chunks
        thread_id: Thread ID
        run_id: Run ID
        
    Yields:
        AG-UI events
    """
    # Emit run started
    yield create_run_started_event(thread_id, run_id)
    
    message_id = str(uuid.uuid4())
    message_started = False
    
    try:
        async for chunk in response_stream:
            if not message_started:
                yield TextMessageStartEvent(message_id=message_id, role="assistant")
                message_started = True
            
            if chunk:
                yield TextMessageContentEvent(message_id=message_id, delta=chunk)
        
        if message_started:
            yield TextMessageEndEvent(message_id=message_id)
        
        # Emit run finished
        yield create_run_finished_event(thread_id, run_id)
        
    except Exception as e:
        if message_started:
            yield TextMessageEndEvent(message_id=message_id)
        yield create_run_error_event(str(e))


def stream_event_to_agui_events(
    event: Any,
    message_id: str,
    buffer: EventBuffer,
) -> List[BaseEvent]:
    """Convert a PraisonAI StreamEvent into zero or more AG-UI events."""
    from praisonaiagents.streaming.events import StreamEventType

    if event.type == StreamEventType.DELTA_TEXT and event.content:
        if not buffer.current_text_message_id:
            buffer.start_text_message()
            return [
                TextMessageStartEvent(message_id=buffer.current_text_message_id, role="assistant"),
                TextMessageContentEvent(
                    message_id=buffer.current_text_message_id, delta=event.content
                ),
            ]
        return [
            TextMessageContentEvent(
                message_id=buffer.current_text_message_id, delta=event.content
            )
        ]

    if event.type == StreamEventType.TOOL_CALL_START and event.tool_call:
        tool_call_id = event.tool_call.get("id") or str(uuid.uuid4())
        tool_name = event.tool_call.get("name", "tool")
        arguments = event.tool_call.get("arguments", {})
        args_str = json.dumps(arguments) if isinstance(arguments, dict) else str(arguments)
        parent_id = buffer.get_parent_message_id_for_tool_call() or message_id
        buffer.start_tool_call(tool_call_id)
        return list(create_tool_call_events(tool_call_id, tool_name, args_str, parent_id))

    if event.type == StreamEventType.TOOL_CALL_RESULT and event.tool_call:
        tool_call_id = event.tool_call.get("id") or str(uuid.uuid4())
        raw_result = event.tool_call.get("result")
        content = event.content if event.content is not None else str(raw_result or "")
        buffer.end_tool_call(tool_call_id)
        events: List[BaseEvent] = [
            create_tool_result_event(tool_call_id, str(content), message_id)
        ]
        if isinstance(raw_result, dict) and raw_result.get("mime_type") == A2UI_MIME_TYPE:
            events.append(
                CustomEvent(
                    name="a2ui",
                    value={
                        "mime_type": A2UI_MIME_TYPE,
                        "messages": raw_result.get("messages", []),
                        "surface_id": _infer_a2ui_surface_id(raw_result),
                    },
                )
            )
        return events

    return []


def _infer_a2ui_surface_id(result: Dict[str, Any]) -> str:
    """Infer surface id from send_a2ui_messages result (inline, no UI-layer deps)."""
    for msg in result.get("messages") or []:
        if isinstance(msg, dict):
            create = msg.get("createSurface")
            if isinstance(create, dict):
                sid = create.get("surfaceId") or create.get("id")
                if sid:
                    return str(sid)
    sid = result.get("surface_id") or result.get("surfaceId")
    return str(sid) if sid else "main"


async def async_stream_agent_response(
    agent,
    user_input: str,
    thread_id: str,
    run_id: str,
    session_state: Optional[Dict[str, Any]] = None,
    messages: Optional[List[Dict[str, Any]]] = None
) -> AsyncIterator[BaseEvent]:
    """
    Stream an agent's response as AG-UI events.
    
    Args:
        agent: PraisonAI Agent instance
        user_input: User input string
        thread_id: Thread ID
        run_id: Run ID
        session_state: Optional session state
        messages: Optional message history
        
    Yields:
        AG-UI events
    """
    yield create_run_started_event(thread_id, run_id)

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    buffer = EventBuffer()
    message_id = str(uuid.uuid4())
    text_started = False
    text_ended = False
    original_emitter = getattr(agent, "stream_emitter", None)

    def on_stream_event(event: Any) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ("stream", event))

    if original_emitter is not None:
        original_emitter.add_callback(on_stream_event)

    async def run_chat() -> Any:
        try:
            if hasattr(agent, "achat"):
                return await agent.achat(user_input, stream=True)
            if hasattr(agent, "chat"):
                return await loop.run_in_executor(
                    None, lambda: agent.chat(user_input, stream=True)
                )
            raise ValueError("Agent must have 'chat' or 'achat' method")
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, ("done", None))

    chat_task = asyncio.create_task(run_chat())

    try:
        while True:
            kind, payload = await queue.get()
            if kind == "done":
                break
            for agui_event in stream_event_to_agui_events(payload, message_id, buffer):
                if isinstance(agui_event, TextMessageStartEvent):
                    text_started = True
                yield agui_event

        response = await chat_task

        if text_started and buffer.current_text_message_id and not text_ended:
            yield TextMessageEndEvent(message_id=buffer.current_text_message_id)
            text_ended = True
        elif not text_started and response:
            yield TextMessageStartEvent(message_id=message_id, role="assistant")
            yield TextMessageContentEvent(message_id=message_id, delta=str(response))
            yield TextMessageEndEvent(message_id=message_id)

        yield create_run_finished_event(thread_id, run_id)

    except Exception as e:
        yield create_run_error_event(str(e))
    finally:
        if original_emitter is not None:
            original_emitter.remove_callback(on_stream_event)


async def async_stream_agents_response(
    agents,
    user_input: str,
    thread_id: str,
    run_id: str,
    session_state: Optional[Dict[str, Any]] = None
) -> AsyncIterator[BaseEvent]:
    """
    Stream a Agents workflow response as AG-UI events.
    
    Args:
        agents: Agents instance
        user_input: User input string
        thread_id: Thread ID
        run_id: Run ID
        session_state: Optional session state
        
    Yields:
        AG-UI events
    """
    # Emit run started
    yield create_run_started_event(thread_id, run_id)
    
    message_id = str(uuid.uuid4())
    
    try:
        # Check if agents has async start method
        if hasattr(agents, 'astart'):
            result = await agents.astart(user_input)
        elif hasattr(agents, 'start'):
            # Run sync start in executor
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, agents.start, user_input)
        else:
            raise ValueError("Agents must have 'start' or 'astart' method")
        
        # Emit text message events with result
        yield TextMessageStartEvent(message_id=message_id, role="assistant")
        
        if result:
            # Handle different result types
            if isinstance(result, dict):
                content = result.get("output", str(result))
            elif hasattr(result, "raw"):
                content = result.raw
            else:
                content = str(result)
            
            yield TextMessageContentEvent(message_id=message_id, delta=content)
        
        yield TextMessageEndEvent(message_id=message_id)
        
        # Emit run finished
        yield create_run_finished_event(thread_id, run_id)
        
    except Exception as e:
        yield create_run_error_event(str(e))
