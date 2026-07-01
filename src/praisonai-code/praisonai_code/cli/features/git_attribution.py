"""
Git Commit Attribution for PraisonAI CLI.

Provides attribution trailers for AI-assisted commits.
"""

import os
import logging
from enum import Enum
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class AttributionStyle(Enum):
    """Attribution styles for git commits."""
    ASSISTED_BY = "assisted-by"
    CO_AUTHORED_BY = "co-authored-by"
    NONE = "none"


@dataclass
class AttributionConfig:
    """Attribution configuration."""
    style: AttributionStyle = AttributionStyle.ASSISTED_BY
    include_model: bool = True
    email: str = "ai@praison.ai"
    name: str = "PraisonAI"


class AttributionManager:
    """
    Manages git commit attribution for AI-assisted changes.
    
    Usage:
        manager = AttributionManager(model="gpt-4o")
        
        # Add attribution to commit message
        message = "Fix bug in parser"
        attributed = manager.add_attribution(message)
        # "Fix bug in parser\n\nAssisted-by: gpt-4o via PraisonAI <ai@praison.ai>"
    """
    
    def __init__(
        self,
        model: Optional[str] = None,
        config: Optional[AttributionConfig] = None,
    ):
        self.model = model or "AI"
        self.config = config or AttributionConfig()
    
    def generate_trailer(self, style: Optional[str] = None) -> str:
        """
        Generate attribution trailer.
        
        Args:
            style: Override style ("assisted-by", "co-authored-by", "none")
            
        Returns:
            Attribution trailer string
        """
        if style:
            try:
                attr_style = AttributionStyle(style)
            except ValueError:
                attr_style = self.config.style
        else:
            attr_style = self.config.style
        
        if attr_style == AttributionStyle.NONE:
            return ""
        
        # Build attribution string
        if self.config.include_model:
            name = f"{self.model} via {self.config.name}"
        else:
            name = self.config.name
        
        if attr_style == AttributionStyle.ASSISTED_BY:
            return f"Assisted-by: {name} <{self.config.email}>"
        elif attr_style == AttributionStyle.CO_AUTHORED_BY:
            return f"Co-Authored-By: {name} <{self.config.email}>"
        
        return ""
    
    def add_attribution(
        self,
        message: str,
        style: Optional[str] = None,
    ) -> str:
        """
        Add attribution trailer to commit message.
        
        Args:
            message: Original commit message
            style: Override attribution style
            
        Returns:
            Commit message with attribution trailer
        """
        trailer = self.generate_trailer(style)
        
        if not trailer:
            return message
        
        # Ensure proper spacing
        message = message.rstrip()
        
        # Check if message already has trailers
        lines = message.split("\n")
        has_trailers = any(
            line.startswith(("Signed-off-by:", "Co-Authored-By:", "Assisted-by:"))
            for line in lines
        )
        
        if has_trailers:
            # Add to existing trailers
            return f"{message}\n{trailer}"
        else:
            # Add new trailer section
            return f"{message}\n\n{trailer}"
    
    def remove_attribution(self, message: str) -> str:
        """Remove PraisonAI attribution from commit message."""
        lines = message.split("\n")
        filtered = [
            line for line in lines
            if not (
                "PraisonAI" in line and
                (line.startswith("Assisted-by:") or line.startswith("Co-Authored-By:"))
            )
        ]
        return "\n".join(filtered).rstrip()


def get_attribution_from_config() -> AttributionManager:
    """Get attribution manager from config."""
    try:
        from .config_hierarchy import load_config
        config = load_config()
        
        attr_config = config.get("attribution", {})
        style_str = attr_config.get("style", "assisted-by")
        
        try:
            style = AttributionStyle(style_str)
        except ValueError:
            style = AttributionStyle.ASSISTED_BY
        
        return AttributionManager(
            model=config.get("model"),
            config=AttributionConfig(
                style=style,
                include_model=attr_config.get("include_model", True),
            )
        )
    except Exception:
        return AttributionManager()
