"""
AG-UI Event Encoder

Encodes AG-UI events to Server-Sent Events (SSE) format.
"""

from praisonaiagents.ui.agui.types import BaseEvent


class EventEncoder:
    """Encodes AG-UI events to SSE format."""
    
    def __init__(self):
        pass
    
    def get_content_type(self) -> str:
        """Returns the content type for SSE."""
        return "text/event-stream"
    
    def encode(self, event: BaseEvent) -> str:
        """
        Encode an event to SSE format.
        
        Args:
            event: The event to encode
            
        Returns:
            SSE formatted string
        """
        return f"data: {event.model_dump_json(by_alias=True, exclude_none=True)}\n\n"
