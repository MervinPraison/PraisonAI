"""
Chat Template for A2UI

Provides a conversational chat UI template.
"""

from typing import Any, Dict, List, Optional

from praisonaiagents.ui.a2ui.surface import Surface
from praisonaiagents.ui.a2ui.extension import STANDARD_CATALOG_ID


class ChatTemplate:
    """
    Chat UI template for conversational interfaces.
    
    Creates a chat-style UI with user and agent messages.
    
    Example:
        >>> template = ChatTemplate(surface_id="chat")
        >>> template.add_user_message("Hello!")
        >>> template.add_agent_message("Hi there! How can I help?")
        >>> messages = template.to_messages()
    """
    
    def __init__(
        self,
        surface_id: str = "chat",
        catalog_id: str = STANDARD_CATALOG_ID,
        title: Optional[str] = None,
    ):
        """
        Initialize ChatTemplate.
        
        Args:
            surface_id: Unique ID for the surface
            catalog_id: Component catalog to use
            title: Optional title for the chat
        """
        self.surface_id = surface_id
        self.catalog_id = catalog_id
        self.title = title
        self.messages: List[Dict[str, Any]] = []
    
    def add_user_message(self, content: str) -> "ChatTemplate":
        """
        Add a user message.
        
        Args:
            content: Message content
        
        Returns:
            self for chaining
        """
        self.messages.append({
            "role": "user",
            "content": content,
        })
        return self
    
    def add_agent_message(self, content: str) -> "ChatTemplate":
        """
        Add an agent message.
        
        Args:
            content: Message content
        
        Returns:
            self for chaining
        """
        self.messages.append({
            "role": "agent",
            "content": content,
        })
        return self
    
    def to_messages(self) -> List[Dict[str, Any]]:
        """
        Generate A2UI messages for the chat.
        
        Returns:
            List of A2UI message dictionaries
        """
        surface = Surface(
            surface_id=self.surface_id,
            catalog_id=self.catalog_id,
        )
        
        children = []
        
        # Title if provided
        if self.title:
            surface.text(id="chat-title", text=self.title, usage_hint="h1")
            children.append("chat-title")
        
        # Message components
        msg_ids = []
        for i, msg in enumerate(self.messages):
            msg_id = f"msg-{i}"
            role = msg["role"]
            content = msg["content"]
            
            # Style based on role
            if role == "user":
                surface.text(id=msg_id, text=f"You: {content}", usage_hint="body")
            else:
                surface.text(id=msg_id, text=f"Agent: {content}", usage_hint="body")
            
            msg_ids.append(msg_id)
        
        # Messages column
        if msg_ids:
            surface.column(id="messages", children=msg_ids)
            children.append("messages")
        
        # Root column
        surface.column(id="root", children=children)
        
        # Set data
        surface.set_data("messages", self.messages)
        
        return surface.to_messages()
