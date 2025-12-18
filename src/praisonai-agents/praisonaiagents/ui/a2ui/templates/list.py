"""
List Template for A2UI

Provides a list UI template for displaying items.
"""

from typing import Any, Dict, List, Optional

from praisonaiagents.ui.a2ui.surface import Surface
from praisonaiagents.ui.a2ui.extension import STANDARD_CATALOG_ID


class ListTemplate:
    """
    List UI template for displaying items.
    
    Creates a list of cards with title, description, and optional image.
    
    Example:
        >>> template = ListTemplate(surface_id="list", title="Results")
        >>> template.add_item(title="Item 1", description="First item")
        >>> template.add_item(title="Item 2", description="Second item")
        >>> messages = template.to_messages()
    """
    
    def __init__(
        self,
        surface_id: str = "list",
        title: str = "Items",
        catalog_id: str = STANDARD_CATALOG_ID,
    ):
        """
        Initialize ListTemplate.
        
        Args:
            surface_id: Unique ID for the surface
            title: List title
            catalog_id: Component catalog to use
        """
        self.surface_id = surface_id
        self.title = title
        self.catalog_id = catalog_id
        self.items: List[Dict[str, Any]] = []
    
    def add_item(
        self,
        title: str,
        description: str = "",
        image_url: Optional[str] = None,
        action: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ListTemplate":
        """
        Add an item to the list.
        
        Args:
            title: Item title
            description: Item description
            image_url: Optional image URL
            action: Optional action name for item button
            metadata: Optional additional metadata
        
        Returns:
            self for chaining
        """
        item = {
            "title": title,
            "description": description,
        }
        if image_url:
            item["image_url"] = image_url
        if action:
            item["action"] = action
        if metadata:
            item.update(metadata)
        
        self.items.append(item)
        return self
    
    def to_messages(self) -> List[Dict[str, Any]]:
        """
        Generate A2UI messages for the list.
        
        Returns:
            List of A2UI message dictionaries
        """
        surface = Surface(
            surface_id=self.surface_id,
            catalog_id=self.catalog_id,
        )
        
        # Title
        surface.text(id="list-title", text=self.title, usage_hint="h1")
        
        # Create cards for each item
        card_ids = []
        for i, item in enumerate(self.items):
            card_id = f"card-{i}"
            content_id = f"content-{i}"
            title_id = f"title-{i}"
            desc_id = f"desc-{i}"
            
            # Item title
            surface.text(id=title_id, text=item["title"], usage_hint="h3")
            
            # Item description
            surface.text(id=desc_id, text=item.get("description", ""), usage_hint="body")
            
            content_children = [title_id, desc_id]
            
            # Optional image
            if item.get("image_url"):
                img_id = f"img-{i}"
                surface.image(id=img_id, url=item["image_url"], usage_hint="smallFeature")
                content_children.insert(0, img_id)
            
            # Optional action button
            if item.get("action"):
                btn_id = f"btn-{i}"
                btn_text_id = f"btn-text-{i}"
                surface.text(id=btn_text_id, text="Select")
                surface.button(
                    id=btn_id,
                    child=btn_text_id,
                    action_name=item["action"],
                    action_context=[{"key": "index", "value": i}],
                    primary=True,
                )
                content_children.append(btn_id)
            
            # Card content
            surface.column(id=content_id, children=content_children)
            
            # Card
            surface.card(id=card_id, child=content_id)
            card_ids.append(card_id)
        
        # Items column
        surface.column(id="items", children=card_ids)
        
        # Root column
        surface.column(id="root", children=["list-title", "items"])
        
        # Set data
        surface.set_data("items", self.items)
        
        return surface.to_messages()
