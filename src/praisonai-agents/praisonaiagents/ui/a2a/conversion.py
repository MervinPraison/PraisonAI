"""
A2A Message Conversion

Convert between A2A protocol messages and PraisonAI internal format.
"""

import json
import uuid
from typing import Any, Dict, List, Optional

from praisonaiagents.ui.a2a.types import (
    Message,
    Role,
    TextPart,
    FilePart,
    DataPart,
    Artifact,
)


def a2a_to_praisonai_messages(messages: List[Message]) -> List[Dict[str, Any]]:
    """
    Convert A2A messages to PraisonAI/OpenAI chat format.
    
    Handles all A2A Part types:
    - TextPart → {"type": "text", "text": ...}
    - FilePart → {"type": "image_url", "image_url": {"url": ...}}
    - DataPart → {"type": "text", "text": json.dumps(data)}
    
    Returns multimodal content list when non-text parts present,
    plain string content when text-only.
    
    Args:
        messages: List of A2A Message objects
        
    Returns:
        List of dicts in OpenAI chat format {"role": ..., "content": ...}
    """
    result = []
    
    for msg in messages:
        # Map A2A role to OpenAI role
        role = "user" if msg.role == Role.USER else "assistant"
        
        content_parts = []
        has_non_text = False
        
        for part in msg.parts:
            if isinstance(part, TextPart):
                content_parts.append({"type": "text", "text": part.text})
            elif isinstance(part, FilePart) and part.file_uri:
                has_non_text = True
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": part.file_uri},
                })
            elif isinstance(part, DataPart):
                has_non_text = True
                content_parts.append({
                    "type": "text",
                    "text": json.dumps(part.data),
                })
            elif hasattr(part, 'text'):
                content_parts.append({"type": "text", "text": part.text})
        
        # Use multimodal list format when non-text parts present,
        # plain string otherwise (backwards compat)
        if has_non_text:
            content = content_parts
        else:
            content = " ".join(p["text"] for p in content_parts)
        
        result.append({
            "role": role,
            "content": content,
        })
    
    return result


def praisonai_to_a2a_message(
    response: str,
    message_id: Optional[str] = None,
    context_id: Optional[str] = None,
    task_id: Optional[str] = None,
) -> Message:
    """
    Convert PraisonAI response to A2A Message.
    
    Args:
        response: Text response from agent
        message_id: Optional message ID (auto-generated if not provided)
        context_id: Optional context ID
        task_id: Optional task ID
        
    Returns:
        A2A Message object
    """
    msg_id = message_id or f"msg-{uuid.uuid4().hex[:12]}"
    
    return Message(
        message_id=msg_id,
        role=Role.AGENT,
        parts=[TextPart(text=response)],
        context_id=context_id,
        task_id=task_id,
    )


def create_artifact(
    content: str,
    artifact_id: Optional[str] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Artifact:
    """
    Create an A2A Artifact from response content.
    
    Args:
        content: Text content for the artifact
        artifact_id: Optional artifact ID (auto-generated if not provided)
        name: Optional artifact name
        description: Optional artifact description
        
    Returns:
        A2A Artifact object
    """
    art_id = artifact_id or f"art-{uuid.uuid4().hex[:12]}"
    
    return Artifact(
        artifact_id=art_id,
        name=name,
        description=description,
        parts=[TextPart(text=content)],
    )


def extract_user_input(messages: List[Message]) -> str:
    """
    Extract the last user input from a list of messages.
    
    Handles all Part types: TextPart text is included directly,
    FilePart URIs noted, DataPart serialized to JSON.
    
    Args:
        messages: List of A2A Message objects
        
    Returns:
        Text content of the last user message, or empty string if none
    """
    # Find the last user message
    for msg in reversed(messages):
        if msg.role == Role.USER:
            content_parts = []
            for part in msg.parts:
                if isinstance(part, TextPart):
                    content_parts.append(part.text)
                elif isinstance(part, FilePart) and part.file_uri:
                    content_parts.append(f"[file: {part.file_uri}]")
                elif isinstance(part, DataPart):
                    content_parts.append(json.dumps(part.data))
                elif hasattr(part, 'text'):
                    content_parts.append(part.text)
            return " ".join(content_parts)
    
    return ""

