"""
A2A Streaming Events

SSE streaming support for A2A task updates.
"""

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
)


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
) -> TaskStatusUpdateEvent:
    """
    Create a TaskStatusUpdateEvent.
    
    Args:
        task_id: Task ID
        state: New task state
        context_id: Optional context ID
        final: Whether this is the final event
        
    Returns:
        TaskStatusUpdateEvent
    """
    return TaskStatusUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        status=TaskStatus(state=state),
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
) -> AsyncIterator[str]:
    """
    Stream agent response as A2A events.
    
    Args:
        agent: PraisonAI Agent instance
        user_input: User input text
        task_id: Task ID
        context_id: Optional context ID
        
    Yields:
        SSE-formatted event strings
    """
    encoder = A2AEventEncoder()
    
    # Emit working status
    working_event = create_status_event(
        task_id=task_id,
        state=TaskState.WORKING,
        context_id=context_id,
    )
    yield encoder.encode_task_status(working_event)
    
    try:
        # Get response from agent
        response = agent.chat(user_input)
        
        # Emit artifact with response
        artifact_event = create_artifact_event(
            task_id=task_id,
            content=str(response),
            context_id=context_id,
            last_chunk=True,
        )
        yield encoder.encode_task_artifact(artifact_event)
        
        # Emit completed status
        completed_event = create_status_event(
            task_id=task_id,
            state=TaskState.COMPLETED,
            context_id=context_id,
            final=True,
        )
        yield encoder.encode_task_status(completed_event)
        
    except Exception:
        # Emit failed status
        failed_event = create_status_event(
            task_id=task_id,
            state=TaskState.FAILED,
            context_id=context_id,
            final=True,
        )
        yield encoder.encode_task_status(failed_event)
    
    # Emit done
    yield encoder.encode_done()
