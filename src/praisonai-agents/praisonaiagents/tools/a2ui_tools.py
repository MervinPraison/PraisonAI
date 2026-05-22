"""
A2UI tools — optional declarative UI via Google's a2ui-agent-sdk.

Usage:
    from praisonaiagents import Agent
    from praisonaiagents.tools.a2ui_tools import send_a2ui_messages

    agent = Agent(name="assistant", tools=[send_a2ui_messages])
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Union

from praisonaiagents.tools.decorator import tool
from praisonaiagents.ui.protocols import A2UI_MIME_TYPE


def _unwrap_messages(messages: Union[List[Dict[str, Any]], Dict[str, Any], str]) -> List[Dict[str, Any]]:
    """Minimal unwrap for common LLM arg shapes (not full UI normalisation)."""
    if isinstance(messages, str):
        try:
            messages = json.loads(messages)
        except json.JSONDecodeError as exc:
            raise ValueError(f"messages JSON string is not valid JSON: {exc}") from exc

    if isinstance(messages, dict):
        if "messages" in messages:
            messages = messages["messages"]
        else:
            messages = [messages]

    if not isinstance(messages, list):
        raise ValueError("messages must be a list of A2UI message dicts or a JSON string")

    return messages


@tool
def send_a2ui_messages(messages: Union[List[Dict[str, Any]], Dict[str, Any], str]) -> Dict[str, Any]:
    """
    Send validated A2UI JSON messages to a connected A2UI renderer client.

    Pass a list of A2UI message dicts (createSurface, updateComponents, etc.)
    or a JSON string. Requires: pip install praisonaiagents[a2ui]

    Args:
        messages: A2UI message list or JSON string from the model.

    Returns:
        Dict with mime_type and serialised messages for A2A/AG-UI clients.
    """
    from praisonaiagents.ui.a2ui.adapter import create_a2ui_part

    messages = _unwrap_messages(messages)

    part = create_a2ui_part({"messages": messages})
    data = getattr(getattr(part, "root", part), "data", messages)
    metadata = getattr(getattr(part, "root", part), "metadata", {}) or {}

    return {
        "mime_type": metadata.get("mimeType", A2UI_MIME_TYPE),
        "messages": messages,
        "a2ui_part": data,
    }
