"""
A2A Streaming Events

SSE streaming support for A2A task updates.
"""

import asyncio
import json
from typing import AsyncIterator, Optional

from praisonaiagents.ui.a2a.types import (
    Task,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    Artifact,
    TextPart,
    Message,
)
from praisonaiagents._logging import get_logger

logger = get_logger(__name__)


class A2AEventEncoder:
    """Encode A2A events for SSE streaming."""
    
    @staticmethod
    def encode_event(event_type: str, data: dict) -> str:
        """
        Encode an event for SSE streaming.
        
        Args:
            event_type: Type of event (e.g., "task.status", "task.artifact")
            data: Event data as dict
            
        Returns:
            SSE-formatted string
        """
        json_data = json.dumps(data, default=str)
        return f"event: {event_type}\ndata: {json_data}\n\n"
    
    @staticmethod
    def encode_task_status(event: TaskStatusUpdateEvent) -> str:
        """Encode TaskStatusUpdateEvent for SSE."""
        data = event.model_dump(by_alias=True, exclude_none=True)
        return A2AEventEncoder.encode_event("task.status", data)
    
    @staticmethod
    def encode_task_artifact(event: TaskArtifactUpdateEvent) -> str:
        """Encode TaskArtifactUpdateEvent for SSE."""
        data = event.model_dump(by_alias=True, exclude_none=True)
        return A2AEventEncoder.encode_event("task.artifact", data)
    
    @staticmethod
    def encode_task(task: Task) -> str:
        """Encode Task object for SSE."""
        data = task.model_dump(by_alias=True, exclude_none=True)
        return A2AEventEncoder.encode_event("task", data)
    
    @staticmethod
    def encode_done() -> str:
        """Encode stream completion event."""
        return "event: done\ndata: {}\n\n"


def create_status_event(
    task_id: str,
    state: TaskState,
    context_id: Optional[str] = None,
    final: bool = False,
    message: Optional[Message] = None,
) -> TaskStatusUpdateEvent:
    """
    Create a TaskStatusUpdateEvent.
    
    Args:
        task_id: Task ID
        state: New task state
        context_id: Optional context ID
        final: Whether this is the final event
        message: Optional status message (e.g. failure reason)
        
    Returns:
        TaskStatusUpdateEvent
    """
    return TaskStatusUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        status=TaskStatus(state=state, message=message),
        final=final,
    )


def create_artifact_event(
    task_id: str,
    content: str,
    artifact_id: Optional[str] = None,
    context_id: Optional[str] = None,
    append: bool = False,
    last_chunk: bool = False,
) -> TaskArtifactUpdateEvent:
    """
    Create a TaskArtifactUpdateEvent.
    
    Args:
        task_id: Task ID
        content: Artifact content
        artifact_id: Optional artifact ID
        context_id: Optional context ID
        append: Whether to append to existing artifact
        last_chunk: Whether this is the last chunk
        
    Returns:
        TaskArtifactUpdateEvent
    """
    import uuid
    art_id = artifact_id or f"art-{uuid.uuid4().hex[:12]}"
    
    artifact = Artifact(
        artifact_id=art_id,
        parts=[TextPart(text=content)],
    )
    
    return TaskArtifactUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        artifact=artifact,
        append=append,
        last_chunk=last_chunk,
    )


async def stream_agent_response(
    agent,
    user_input: str,
    task_id: str,
    context_id: Optional[str] = None,
    *,
    task_store=None,
    running: Optional[dict] = None,
) -> AsyncIterator[str]:
    """
    Stream agent response as A2A events.
    
    The sync agent call runs in a worker thread so the event loop stays
    responsive. When ``task_store``/``running`` are given, the task's
    lifecycle is mirrored into the store and the call is registered so
    ``tasks/get`` and ``tasks/cancel`` work for streamed tasks.
    
    Args:
        agent: PraisonAI Agent (uses ``chat``) or AgentTeam (uses ``start``)
        user_input: User input text
        task_id: Task ID
        context_id: Optional context ID
        task_store: Optional TaskStore to keep in sync
        running: Optional dict of task_id -> future, used for cancellation
        
    Yields:
        SSE-formatted event strings
    """
    from praisonaiagents.ui.a2a.conversion import praisonai_to_a2a_message
    
    encoder = A2AEventEncoder()
    
    if task_store is not None:
        task_store.update_status(task_id, TaskState.WORKING)
        # Keep the task while the agent runs: a cancel can make it
        # terminal (and evictable) before we finish.
        task_store._pinned.add(task_id)
    
    # Emit working status
    yield encoder.encode_task_status(create_status_event(
        task_id=task_id,
        state=TaskState.WORKING,
        context_id=context_id,
    ))
    
    fut = None
    try:
        call = agent.chat if hasattr(agent, "chat") else agent.start
        fut = asyncio.ensure_future(asyncio.to_thread(call, user_input))
        if running is not None:
            running[task_id] = fut
        response = str(await fut)
        
        artifact_event = create_artifact_event(
            task_id=task_id,
            content=response,
            context_id=context_id,
            last_chunk=True,
        )
        if task_store is not None:
            task_store.add_to_history(
                task_id, praisonai_to_a2a_message(response, task_id=task_id)
            )
            task_store.add_artifact(task_id, artifact_event.artifact)
            task_store.update_status(task_id, TaskState.COMPLETED)
        yield encoder.encode_task_artifact(artifact_event)
        
        yield encoder.encode_task_status(create_status_event(
            task_id=task_id,
            state=TaskState.COMPLETED,
            context_id=context_id,
            final=True,
        ))
    
    except asyncio.CancelledError:
        # tasks/cancel marks the task CANCELLED before cancelling the call;
        # report that to the client. Any other cancellation (e.g. client
        # disconnect) is propagated.
        task = task_store.get_task(task_id) if task_store is not None else None
        if task is None or task.status.state != TaskState.CANCELLED:
            if task_store is not None:
                task_store.update_status(task_id, TaskState.CANCELLED)
            raise
        yield encoder.encode_task_status(create_status_event(
            task_id=task_id,
            state=TaskState.CANCELLED,
            context_id=context_id,
            final=True,
        ))
    
    except Exception as e:
        logger.error("A2A stream failed for task %s: %s", task_id, e, exc_info=True)
        reason = praisonai_to_a2a_message(str(e), task_id=task_id)
        if task_store is not None:
            task_store.update_status(task_id, TaskState.FAILED, message=reason)
        yield encoder.encode_task_status(create_status_event(
            task_id=task_id,
            state=TaskState.FAILED,
            context_id=context_id,
            final=True,
            message=reason,
        ))
    
    finally:
        if running is not None and running.get(task_id) is fut:
            running.pop(task_id, None)
        if task_store is not None:
            task_store._pinned.discard(task_id)
    
    # Emit done
    yield encoder.encode_done()
