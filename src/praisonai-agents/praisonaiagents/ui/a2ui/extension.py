"""
A2UI Extension for A2A Protocol

Provides helpers for integrating A2UI with the A2A (Agent-to-Agent) protocol.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from praisonaiagents.ui.a2ui.types import A2UIDataPart


# =============================================================================
# Constants
# =============================================================================

A2UI_EXTENSION_URI = "https://a2ui.org/a2a-extension/a2ui/v0.9"
A2UI_MIME_TYPE = "application/json+a2ui"
STANDARD_CATALOG_ID = "https://raw.githubusercontent.com/google/A2UI/refs/heads/main/specification/0.9/json/standard_catalog_definition.json"


# =============================================================================
# Agent Extension Type
# =============================================================================

@dataclass
class AgentExtension:
    """
    A2A Agent Extension configuration.
    
    Describes an extension that an agent supports.
    """
    uri: str
    description: str = ""
    params: Optional[Dict[str, Any]] = None


# =============================================================================
# Helper Functions
# =============================================================================

def create_a2ui_part(a2ui_data: Dict[str, Any]) -> A2UIDataPart:
    """
    Create an A2UI data part for A2A integration.
    
    Wraps A2UI data in an A2UIDataPart with the appropriate MIME type.
    
    Args:
        a2ui_data: The A2UI data dictionary (e.g., createSurface, updateComponents)
    
    Returns:
        An A2UIDataPart with the A2UI MIME type in metadata
    
    Example:
        >>> part = create_a2ui_part({"createSurface": {"surfaceId": "main", "catalogId": "..."}})
        >>> part.metadata["mimeType"]
        'application/json+a2ui'
    """
    return A2UIDataPart(
        data=a2ui_data,
        metadata={"mimeType": A2UI_MIME_TYPE}
    )


def is_a2ui_part(part: A2UIDataPart) -> bool:
    """
    Check if a data part contains A2UI data.
    
    Args:
        part: The data part to check
    
    Returns:
        True if the part contains A2UI data (has A2UI MIME type), False otherwise
    
    Example:
        >>> part = create_a2ui_part({"createSurface": {...}})
        >>> is_a2ui_part(part)
        True
    """
    if not isinstance(part, A2UIDataPart):
        return False
    if part.metadata is None:
        return False
    return part.metadata.get("mimeType") == A2UI_MIME_TYPE


def get_a2ui_agent_extension(
    accepts_inline_custom_catalog: bool = False,
) -> AgentExtension:
    """
    Create the A2UI AgentExtension configuration.
    
    Returns an AgentExtension that can be added to an A2A Agent Card
    to indicate A2UI support.
    
    Args:
        accepts_inline_custom_catalog: Whether the agent accepts inline custom catalogs
    
    Returns:
        The configured A2UI AgentExtension
    
    Example:
        >>> ext = get_a2ui_agent_extension()
        >>> ext.uri
        'https://a2ui.org/a2a-extension/a2ui/v0.9'
    """
    params: Optional[Dict[str, Any]] = None
    if accepts_inline_custom_catalog:
        params = {"acceptsInlineCustomCatalog": True}
    
    return AgentExtension(
        uri=A2UI_EXTENSION_URI,
        description="Provides agent-driven UI using the A2UI JSON format.",
        params=params
    )
