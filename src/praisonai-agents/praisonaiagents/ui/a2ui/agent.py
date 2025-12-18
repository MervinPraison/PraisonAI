"""
A2UI Agent Integration

Provides A2UIAgent wrapper for generating A2UI responses from PraisonAI agents.
"""

import uuid
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from praisonaiagents.ui.a2ui.surface import Surface
from praisonaiagents.ui.a2ui.types import (
    PathBinding,
    A2UIDataPart,
)
from praisonaiagents.ui.a2ui.extension import (
    create_a2ui_part,
    STANDARD_CATALOG_ID,
)

if TYPE_CHECKING:
    from praisonaiagents import Agent


class A2UIAgent:
    """
    A2UI wrapper for PraisonAI agents.
    
    Provides methods to generate A2UI responses from agent interactions.
    
    Example:
        >>> from praisonaiagents import Agent
        >>> from praisonaiagents.ui.a2ui import A2UIAgent
        >>> 
        >>> agent = Agent(name="Assistant", role="Helper", goal="Help users")
        >>> a2ui_agent = A2UIAgent(agent=agent)
        >>> 
        >>> # Render a simple text response
        >>> messages = a2ui_agent.render_text("Hello, World!")
        >>> 
        >>> # Render a list of items
        >>> messages = a2ui_agent.render_list(
        ...     title="Results",
        ...     items=[{"name": "Item 1"}, {"name": "Item 2"}]
        ... )
    """
    
    def __init__(
        self,
        agent: "Agent",
        surface_id: Optional[str] = None,
        catalog_id: str = STANDARD_CATALOG_ID,
    ):
        """
        Initialize A2UIAgent wrapper.
        
        Args:
            agent: The PraisonAI Agent to wrap
            surface_id: Unique ID for the UI surface (auto-generated if not provided)
            catalog_id: The component catalog to use
        """
        self.agent = agent
        self.surface_id = surface_id or f"surface-{uuid.uuid4().hex[:8]}"
        self.catalog_id = catalog_id
        self._surface: Optional[Surface] = None
    
    def get_surface(self) -> Surface:
        """
        Get the underlying Surface object.
        
        Creates a new Surface if one doesn't exist.
        
        Returns:
            The Surface object
        """
        if self._surface is None:
            self._surface = Surface(
                surface_id=self.surface_id,
                catalog_id=self.catalog_id,
            )
        return self._surface
    
    def _reset_surface(self) -> Surface:
        """Reset and return a new Surface."""
        self._surface = Surface(
            surface_id=self.surface_id,
            catalog_id=self.catalog_id,
        )
        return self._surface
    
    # =========================================================================
    # Rendering methods
    # =========================================================================
    
    def render_text(
        self,
        text: str,
        title: Optional[str] = None,
        usage_hint: str = "body",
    ) -> List[Dict[str, Any]]:
        """
        Render a simple text response as A2UI.
        
        Args:
            text: The text content to display
            title: Optional title heading
            usage_hint: Text style hint (h1, h2, body, caption)
        
        Returns:
            List of A2UI message dictionaries
        """
        surface = self._reset_surface()
        
        children = []
        
        if title:
            surface.text(id="title", text=title, usage_hint="h1")
            children.append("title")
        
        surface.text(id="content", text=text, usage_hint=usage_hint)
        children.append("content")
        
        # Add root column
        surface.column(id="root", children=children)
        
        return surface.to_messages()
    
    def render_list(
        self,
        title: str,
        items: List[Dict[str, Any]],
        item_title_key: str = "title",
        item_description_key: str = "description",
        item_image_key: Optional[str] = None,
        item_action: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Render a list of items as A2UI cards.
        
        Args:
            title: List title
            items: List of item dictionaries
            item_title_key: Key for item title in each dict
            item_description_key: Key for item description
            item_image_key: Optional key for item image URL
            item_action: Optional action name for item buttons
        
        Returns:
            List of A2UI message dictionaries
        """
        surface = self._reset_surface()
        
        # Title
        surface.text(id="list-title", text=title, usage_hint="h1")
        
        # Create card for each item
        card_ids = []
        for i, item in enumerate(items):
            card_id = f"card-{i}"
            content_id = f"card-content-{i}"
            title_id = f"item-title-{i}"
            desc_id = f"item-desc-{i}"
            
            # Item title
            surface.text(
                id=title_id,
                text=item.get(item_title_key, f"Item {i+1}"),
                usage_hint="h3"
            )
            
            # Item description
            surface.text(
                id=desc_id,
                text=item.get(item_description_key, ""),
                usage_hint="body"
            )
            
            content_children = [title_id, desc_id]
            
            # Optional action button
            if item_action:
                btn_id = f"btn-{i}"
                btn_text_id = f"btn-text-{i}"
                surface.text(id=btn_text_id, text="Select")
                surface.button(
                    id=btn_id,
                    child=btn_text_id,
                    action_name=item_action,
                    action_context=[{"key": "index", "value": i}],
                    primary=True
                )
                content_children.append(btn_id)
            
            # Card content column
            surface.column(id=content_id, children=content_children)
            
            # Card
            surface.card(id=card_id, child=content_id)
            card_ids.append(card_id)
        
        # List column
        surface.column(id="item-list", children=card_ids)
        
        # Root column
        surface.column(id="root", children=["list-title", "item-list"])
        
        # Set data
        surface.set_data("items", items)
        
        return surface.to_messages()
    
    def render_form(
        self,
        title: str,
        fields: List[Dict[str, str]],
        submit_action: str = "submit",
        submit_label: str = "Submit",
    ) -> List[Dict[str, Any]]:
        """
        Render a form as A2UI.
        
        Args:
            title: Form title
            fields: List of field definitions with id, label, type
            submit_action: Action name for submit button
            submit_label: Label for submit button
        
        Returns:
            List of A2UI message dictionaries
        """
        surface = self._reset_surface()
        
        # Title
        surface.text(id="form-title", text=title, usage_hint="h1")
        
        # Fields
        field_ids = []
        form_data = {}
        
        for field in fields:
            field_id = field.get("id", f"field-{len(field_ids)}")
            label = field.get("label", field_id)
            field_type = field.get("type", "text")
            
            surface.text_field(
                id=field_id,
                label=label,
                text=PathBinding(path=f"/{field_id}"),
                field_type=field_type,
            )
            field_ids.append(field_id)
            form_data[field_id] = field.get("default", "")
        
        # Submit button
        surface.text(id="submit-text", text=submit_label)
        
        # Build action context from fields
        action_context = [
            {"key": f["id"], "value": {"path": f"/{f['id']}"}}
            for f in fields
        ]
        
        surface.button(
            id="submit-btn",
            child="submit-text",
            action_name=submit_action,
            action_context=action_context,
            primary=True,
        )
        field_ids.append("submit-btn")
        
        # Form column
        surface.column(id="form-fields", children=field_ids)
        
        # Root column
        surface.column(id="root", children=["form-title", "form-fields"])
        
        # Set initial form data
        for key, value in form_data.items():
            surface.set_data(key, value)
        
        return surface.to_messages()
    
    # =========================================================================
    # Agent interaction methods
    # =========================================================================
    
    async def chat_async(self, message: str) -> str:
        """
        Send a message to the agent and get a response.
        
        Args:
            message: The message to send
        
        Returns:
            The agent's response text
        """
        # Use the agent's chat method
        if hasattr(self.agent, 'chat'):
            response = self.agent.chat(message)
            return response
        elif hasattr(self.agent, 'run'):
            response = self.agent.run(message)
            return response
        else:
            raise NotImplementedError("Agent does not have chat or run method")
    
    def chat(self, message: str) -> str:
        """
        Send a message to the agent and get a response (sync).
        
        Args:
            message: The message to send
        
        Returns:
            The agent's response text
        """
        if hasattr(self.agent, 'chat'):
            return self.agent.chat(message)
        elif hasattr(self.agent, 'run'):
            return self.agent.run(message)
        else:
            raise NotImplementedError("Agent does not have chat or run method")
    
    # =========================================================================
    # Export methods
    # =========================================================================
    
    def to_messages(self) -> List[Dict[str, Any]]:
        """
        Get the current surface as A2UI messages.
        
        Returns:
            List of A2UI message dictionaries
        """
        return self.get_surface().to_messages()
    
    def to_json(self, indent: Optional[int] = None) -> str:
        """
        Get the current surface as JSON string.
        
        Args:
            indent: JSON indentation level
        
        Returns:
            JSON string of A2UI messages
        """
        return self.get_surface().to_json(indent=indent)
    
    def to_a2a_part(self) -> A2UIDataPart:
        """
        Get the current surface as an A2A DataPart.
        
        Returns:
            A2UIDataPart with A2UI MIME type
        """
        messages = self.to_messages()
        # For A2A, we send messages as a list
        return create_a2ui_part({"messages": messages})
