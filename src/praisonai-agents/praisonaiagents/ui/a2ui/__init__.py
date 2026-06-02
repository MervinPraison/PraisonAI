"""
A2UI integration via Google's a2ui-agent-sdk (optional).

Declarative agent UI uses the official SDK — not reimplemented in PraisonAI core.
Install: pip install praisonaiagents[a2ui]
"""

from praisonaiagents.ui.a2ui.adapter import (
    create_a2ui_part,
    generate_a2ui_system_prompt,
    get_schema_manager,
    is_a2ui_part,
    parse_a2ui_response,
)
from praisonaiagents.ui.protocols import A2UI_MIME_TYPE, A2UIToolResultProtocol

__all__ = [
    "A2UI",
    "A2UI_MIME_TYPE",
    "A2UIToolResultProtocol",
    "create_a2ui_part",
    "generate_a2ui_system_prompt",
    "get_schema_manager",
    "is_a2ui_part",
    "parse_a2ui_response",
]


class A2UI:
    """
    Optional A2UI facade (lazy — imports a2ui-agent-sdk on first use).

    Example:
        from praisonaiagents.ui import A2UI

        part = A2UI.create_part({"createSurface": {...}})
        prompt = A2UI.system_prompt("You are a helpful assistant.")
    """

    create_part = staticmethod(create_a2ui_part)
    is_part = staticmethod(is_a2ui_part)
    parse_response = staticmethod(parse_a2ui_response)
    schema_manager = staticmethod(get_schema_manager)
    system_prompt = staticmethod(generate_a2ui_system_prompt)
