"""
A2UI Surface Builder

Provides a fluent API for building A2UI surfaces with components and data.
"""

import json
from typing import Any, Dict, List, Optional

from praisonaiagents.ui.a2ui.extension import STANDARD_CATALOG_ID
from praisonaiagents.ui.a2ui.types import (
    Component,
    TextComponent,
    ImageComponent,
    ButtonComponent,
    CardComponent,
    RowComponent,
    ColumnComponent,
    ListComponent,
    TextFieldComponent,
    Action,
    ActionContext,
    PathBinding,
    CreateSurfaceMessage,
    UpdateComponentsMessage,
    UpdateDataModelMessage,
    StringOrPath,
    ChildrenType,
)


class Surface:
    """
    A2UI Surface builder for creating rich agent-generated UIs.
    
    Provides a fluent API for adding components and data, then
    generating the A2UI JSON messages.
    
    Example:
        >>> surface = Surface(surface_id="main")
        >>> surface.text(id="title", text="Hello World", usage_hint="h1")
        >>> surface.button(id="submit", child="submit-text", action_name="submit")
        >>> surface.set_data("title", "Hello World")
        >>> messages = surface.to_messages()
    """
    
    def __init__(
        self,
        surface_id: str,
        catalog_id: str = STANDARD_CATALOG_ID,
    ):
        """
        Initialize a new Surface.
        
        Args:
            surface_id: Unique identifier for this surface
            catalog_id: The component catalog to use (defaults to standard catalog)
        """
        self.surface_id = surface_id
        self.catalog_id = catalog_id
        self.components: List[Component] = []
        self.data: Dict[str, Any] = {}
    
    def add(self, component: Component) -> "Surface":
        """
        Add a component to the surface.
        
        Args:
            component: The component to add
        
        Returns:
            self for method chaining
        """
        self.components.append(component)
        return self
    
    def set_data(self, key: str, value: Any) -> "Surface":
        """
        Set a value in the data model.
        
        Args:
            key: The key in the data model
            value: The value to set
        
        Returns:
            self for method chaining
        """
        self.data[key] = value
        return self
    
    # =========================================================================
    # Helper methods for common components
    # =========================================================================
    
    def text(
        self,
        id: str,
        text: StringOrPath,
        usage_hint: Optional[str] = None,
        weight: Optional[float] = None,
    ) -> "Surface":
        """
        Add a Text component.
        
        Args:
            id: Component ID
            text: Text content or path binding
            usage_hint: Style hint (h1, h2, h3, body, caption)
            weight: Flex weight
        
        Returns:
            self for method chaining
        """
        return self.add(TextComponent(
            id=id,
            text=text,
            usage_hint=usage_hint,
            weight=weight,
        ))
    
    def image(
        self,
        id: str,
        url: StringOrPath,
        fit: Optional[str] = None,
        usage_hint: Optional[str] = None,
        weight: Optional[float] = None,
    ) -> "Surface":
        """
        Add an Image component.
        
        Args:
            id: Component ID
            url: Image URL or path binding
            fit: Image fit (contain, cover, fill, none, scale-down)
            usage_hint: Size hint (icon, avatar, smallFeature, etc.)
            weight: Flex weight
        
        Returns:
            self for method chaining
        """
        return self.add(ImageComponent(
            id=id,
            url=url,
            fit=fit,
            usage_hint=usage_hint,
            weight=weight,
        ))
    
    def button(
        self,
        id: str,
        child: str,
        action_name: Optional[str] = None,
        action_context: Optional[List[Dict[str, Any]]] = None,
        primary: bool = False,
        weight: Optional[float] = None,
    ) -> "Surface":
        """
        Add a Button component.
        
        Args:
            id: Component ID
            child: Child component ID (usually a Text component)
            action_name: Name of the action to trigger
            action_context: List of {key, value} dicts for action context
            primary: Whether this is a primary button
            weight: Flex weight
        
        Returns:
            self for method chaining
        """
        action = None
        if action_name:
            context = []
            if action_context:
                for ctx in action_context:
                    value = ctx.get("value")
                    if isinstance(value, dict) and "path" in value:
                        value = PathBinding(path=value["path"])
                    context.append(ActionContext(key=ctx["key"], value=value))
            action = Action(name=action_name, context=context)
        
        return self.add(ButtonComponent(
            id=id,
            child=child,
            action=action,
            primary=primary,
            weight=weight,
        ))
    
    def card(
        self,
        id: str,
        child: str,
        weight: Optional[float] = None,
    ) -> "Surface":
        """
        Add a Card component.
        
        Args:
            id: Component ID
            child: Child component ID
            weight: Flex weight
        
        Returns:
            self for method chaining
        """
        return self.add(CardComponent(
            id=id,
            child=child,
            weight=weight,
        ))
    
    def row(
        self,
        id: str,
        children: ChildrenType,
        weight: Optional[float] = None,
    ) -> "Surface":
        """
        Add a Row (horizontal layout) component.
        
        Args:
            id: Component ID
            children: List of child IDs or ChildrenTemplate
            weight: Flex weight
        
        Returns:
            self for method chaining
        """
        return self.add(RowComponent(
            id=id,
            children=children,
            weight=weight,
        ))
    
    def column(
        self,
        id: str,
        children: ChildrenType,
        weight: Optional[float] = None,
    ) -> "Surface":
        """
        Add a Column (vertical layout) component.
        
        Args:
            id: Component ID
            children: List of child IDs or ChildrenTemplate
            weight: Flex weight
        
        Returns:
            self for method chaining
        """
        return self.add(ColumnComponent(
            id=id,
            children=children,
            weight=weight,
        ))
    
    def list(
        self,
        id: str,
        children: ChildrenType,
        direction: str = "vertical",
        weight: Optional[float] = None,
    ) -> "Surface":
        """
        Add a List component.
        
        Args:
            id: Component ID
            children: List of child IDs or ChildrenTemplate for dynamic lists
            direction: "vertical" or "horizontal"
            weight: Flex weight
        
        Returns:
            self for method chaining
        """
        return self.add(ListComponent(
            id=id,
            children=children,
            direction=direction,
            weight=weight,
        ))
    
    def text_field(
        self,
        id: str,
        label: StringOrPath,
        text: StringOrPath,
        field_type: str = "text",
        weight: Optional[float] = None,
    ) -> "Surface":
        """
        Add a TextField input component.
        
        Args:
            id: Component ID
            label: Field label
            text: Text value or path binding
            field_type: Input type (text, number, email, etc.)
            weight: Flex weight
        
        Returns:
            self for method chaining
        """
        return self.add(TextFieldComponent(
            id=id,
            label=label,
            text=text,
            field_type=field_type,
            weight=weight,
        ))
    
    # =========================================================================
    # Message generation
    # =========================================================================
    
    def to_messages(self) -> List[Dict[str, Any]]:
        """
        Generate A2UI messages for this surface.
        
        Returns:
            List of A2UI message dictionaries
        """
        messages: List[Dict[str, Any]] = []
        
        # 1. CreateSurface message
        create_msg = CreateSurfaceMessage(
            surface_id=self.surface_id,
            catalog_id=self.catalog_id,
        )
        messages.append(create_msg.to_dict())
        
        # 2. UpdateComponents message (if we have components)
        if self.components:
            update_msg = UpdateComponentsMessage(
                surface_id=self.surface_id,
                components=self.components,
            )
            messages.append(update_msg.to_dict())
        
        # 3. UpdateDataModel message (if we have data)
        if self.data:
            data_msg = UpdateDataModelMessage(
                surface_id=self.surface_id,
                value=self.data,
            )
            messages.append(data_msg.to_dict())
        
        return messages
    
    def to_json(self, indent: Optional[int] = None) -> str:
        """
        Generate A2UI messages as a JSON string.
        
        Args:
            indent: JSON indentation level (None for compact)
        
        Returns:
            JSON string of A2UI messages
        """
        return json.dumps(self.to_messages(), indent=indent)
