"""
UI protocol types — lightweight contracts for agent-to-UI integration.

Zero runtime cost: TypedDict and constants only. No optional dependencies.
"""

from __future__ import annotations

from typing import Any, Dict, List, TypedDict, Union

# Standard MIME type for A2UI payloads (Google A2UI / A2A transport).
A2UI_MIME_TYPE = "application/json+a2ui"


class A2UIToolResultProtocol(TypedDict, total=False):
    """
    Output shape from ``send_a2ui_messages`` — the integrator contract for any UI.

    Example:
        if result.get("mime_type") == A2UI_MIME_TYPE:
            render(result["messages"])
    """

    mime_type: str
    messages: List[Dict[str, Any]]
    a2ui_part: Union[Dict[str, Any], List[Any]]
