"""
AG-UI Message Conversion

Converts between AG-UI message format and PraisonAI message format.
"""

import logging
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel

from praisonaiagents.ui.agui.types import Message, ToolCall, FunctionCall

logger = logging.getLogger(__name__)


def agui_messages_to_praisonai(messages: List[Message]) -> List[Dict[str, Any]]:
    """
    Convert AG-UI messages to PraisonAI format.
    
    Args:
        messages: List of AG-UI Message objects
        
    Returns:
        List of message dictionaries in PraisonAI format
    """
    if not messages:
        return []
    
    # Track tool_call_ids that have results to avoid duplicates
    tool_call_ids_with_results: Set[str] = set()
    for msg in messages:
        if msg.role == "tool" and msg.tool_call_id:
            tool_call_ids_with_results.add(msg.tool_call_id)
    
    result: List[Dict[str, Any]] = []
    seen_tool_call_ids: Set[str] = set()
    
    for msg in messages:
        # Skip system messages - agent builds its own
        if msg.role == "system":
            continue
        
        if msg.role == "tool":
            # Deduplicate tool results
            if msg.tool_call_id in seen_tool_call_ids:
                logger.debug(f"Skipping duplicate tool result: {msg.tool_call_id}")
                continue
            if msg.tool_call_id:
                seen_tool_call_ids.add(msg.tool_call_id)
            
            result.append({
                "role": "tool",
                "content": msg.content or "",
                "tool_call_id": msg.tool_call_id,
            })
        
        elif msg.role == "assistant":
            msg_dict: Dict[str, Any] = {
                "role": "assistant",
                "content": msg.content or "",
            }
            
            if msg.tool_calls:
                # Include all tool_calls (filtering only when there are results to match)
                tool_calls_list = [
                    {
                        "id": tc.id,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                        "type": "function",
                    }
                    for tc in msg.tool_calls
                ]
                if tool_calls_list:
                    msg_dict["tool_calls"] = tool_calls_list
            
            result.append(msg_dict)
        
        elif msg.role == "user":
            result.append({
                "role": "user",
                "content": msg.content or "",
            })
        
        else:
            logger.warning(f"Unknown message role: {msg.role}")
    
    return result


def praisonai_messages_to_agui(messages: List[Dict[str, Any]]) -> List[Message]:
    """
    Convert PraisonAI messages to AG-UI format.
    
    Args:
        messages: List of message dictionaries in PraisonAI format
        
    Returns:
        List of AG-UI Message objects
    """
    if not messages:
        return []
    
    result: List[Message] = []
    
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        
        if role == "tool":
            result.append(Message(
                role="tool",
                content=content,
                tool_call_id=msg.get("tool_call_id"),
            ))
        
        elif role == "assistant":
            tool_calls = None
            if "tool_calls" in msg and msg["tool_calls"]:
                tool_calls = [
                    ToolCall(
                        id=tc.get("id", ""),
                        function=FunctionCall(
                            name=tc.get("function", {}).get("name", ""),
                            arguments=tc.get("function", {}).get("arguments", "{}"),
                        ),
                    )
                    for tc in msg["tool_calls"]
                ]
            
            result.append(Message(
                role="assistant",
                content=content,
                tool_calls=tool_calls,
            ))
        
        elif role == "user":
            result.append(Message(
                role="user",
                content=content,
            ))
        
        elif role == "system":
            result.append(Message(
                role="system",
                content=content,
            ))
    
    return result


def validate_state(state: Any, thread_id: str) -> Optional[Dict[str, Any]]:
    """
    Validate and convert state to a dictionary.
    
    Args:
        state: The state to validate (can be dict, Pydantic model, or other)
        thread_id: Thread ID for logging
        
    Returns:
        State as a dictionary, or None if invalid
    """
    if state is None:
        return None
    
    if isinstance(state, dict):
        return state
    
    if isinstance(state, BaseModel):
        try:
            return state.model_dump()
        except Exception:
            pass
    
    # Try to_dict method
    if hasattr(state, "to_dict") and callable(getattr(state, "to_dict")):
        try:
            result = state.to_dict()
            if isinstance(result, dict):
                return result
        except Exception:
            pass
    
    logger.warning(
        f"State must be a dict, got {type(state).__name__}. "
        f"State will be ignored. Thread: {thread_id}"
    )
    return None


def extract_user_input(messages: List[Message]) -> str:
    """
    Extract the last user message content.
    
    Args:
        messages: List of AG-UI messages
        
    Returns:
        Content of the last user message, or empty string
    """
    if not messages:
        return ""
    
    for msg in reversed(messages):
        if msg.role == "user" and msg.content:
            return msg.content
    
    return ""
