"""
Dashboard Template for A2UI

Provides a dashboard UI template with multiple panels.
"""

from typing import Any, Dict, List, Optional

from praisonaiagents.ui.a2ui.surface import Surface
from praisonaiagents.ui.a2ui.extension import STANDARD_CATALOG_ID


class DashboardTemplate:
    """
    Dashboard UI template with multiple panels.
    
    Creates a dashboard layout with cards for each panel.
    
    Example:
        >>> template = DashboardTemplate(surface_id="dashboard", title="My Dashboard")
        >>> template.add_panel(id="stats", title="Statistics", content="100 items")
        >>> template.add_panel(id="chart", title="Chart", content="[Chart here]")
        >>> messages = template.to_messages()
    """
    
    def __init__(
        self,
        surface_id: str = "dashboard",
        title: str = "Dashboard",
        catalog_id: str = STANDARD_CATALOG_ID,
        columns: int = 2,
    ):
        """
        Initialize DashboardTemplate.
        
        Args:
            surface_id: Unique ID for the surface
            title: Dashboard title
            catalog_id: Component catalog to use
            columns: Number of columns in the grid
        """
        self.surface_id = surface_id
        self.title = title
        self.catalog_id = catalog_id
        self.columns = columns
        self.panels: List[Dict[str, Any]] = []
    
    def add_panel(
        self,
        id: str,
        title: str,
        content: str,
        weight: Optional[float] = None,
    ) -> "DashboardTemplate":
        """
        Add a panel to the dashboard.
        
        Args:
            id: Panel ID
            title: Panel title
            content: Panel content text
            weight: Optional flex weight
        
        Returns:
            self for chaining
        """
        self.panels.append({
            "id": id,
            "title": title,
            "content": content,
            "weight": weight,
        })
        return self
    
    def to_messages(self) -> List[Dict[str, Any]]:
        """
        Generate A2UI messages for the dashboard.
        
        Returns:
            List of A2UI message dictionaries
        """
        surface = Surface(
            surface_id=self.surface_id,
            catalog_id=self.catalog_id,
        )
        
        # Title
        surface.text(id="dashboard-title", text=self.title, usage_hint="h1")
        
        # Create cards for each panel
        card_ids = []
        for panel in self.panels:
            panel_id = panel["id"]
            content_id = f"{panel_id}-content"
            title_id = f"{panel_id}-title"
            text_id = f"{panel_id}-text"
            
            # Panel title
            surface.text(id=title_id, text=panel["title"], usage_hint="h3")
            
            # Panel content
            surface.text(id=text_id, text=panel["content"], usage_hint="body")
            
            # Panel content column
            surface.column(id=content_id, children=[title_id, text_id])
            
            # Panel card
            surface.card(id=panel_id, child=content_id, weight=panel.get("weight"))
            card_ids.append(panel_id)
        
        # Arrange panels in rows based on columns setting
        row_ids = []
        for i in range(0, len(card_ids), self.columns):
            row_cards = card_ids[i:i + self.columns]
            row_id = f"row-{i // self.columns}"
            surface.row(id=row_id, children=row_cards)
            row_ids.append(row_id)
        
        # Panels container
        surface.column(id="panels", children=row_ids)
        
        # Root column
        surface.column(id="root", children=["dashboard-title", "panels"])
        
        # Set data
        surface.set_data("panels", self.panels)
        
        return surface.to_messages()
