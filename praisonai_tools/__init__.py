"""PraisonAI Tools - External tool collection for PraisonAI agents.

This package provides external tools that can be used with PraisonAI agents.
Tools follow the lazy loading pattern to minimize import overhead.

Usage:
    from praisonai_tools import heygen_generate_video, heygen_list_avatars
    
    # Or import the class directly
    from praisonai_tools.tools.heygen_tool import HeyGenTool
"""

from typing import Any, Dict, List
import importlib
import logging

logger = logging.getLogger(__name__)

# Available tools (lazy loaded via __getattr__)
__all__ = [
    "heygen_generate_video",
    "heygen_list_avatars", 
    "heygen_list_voices",
    "heygen_video_status",
    "HeyGenTool",
    # Decorated versions for direct agent use
    "heygen_list_avatars_tool",
    "heygen_list_voices_tool",
    "heygen_generate_video_tool", 
    "heygen_video_status_tool",
]


def __getattr__(name: str) -> Any:
    """Lazy loading of tools to avoid import overhead."""
    
    if name in {"heygen_generate_video", "heygen_list_avatars", "heygen_list_voices", "heygen_video_status"}:
        try:
            from .tools.heygen_tool import heygen_generate_video, heygen_list_avatars, heygen_list_voices, heygen_video_status
            globals()[name] = locals()[name]
            return locals()[name]
        except ImportError as e:
            logger.error(f"Failed to import {name}: {e}")
            raise
    
    if name == "HeyGenTool":
        try:
            from .tools.heygen_tool import HeyGenTool
            globals()["HeyGenTool"] = HeyGenTool
            return HeyGenTool
        except ImportError as e:
            logger.error(f"Failed to import HeyGenTool: {e}")
            raise
    
    # Decorated tool versions
    if name in {"heygen_list_avatars_tool", "heygen_list_voices_tool", "heygen_generate_video_tool", "heygen_video_status_tool"}:
        try:
            from .decorators import (
                heygen_list_avatars_tool, heygen_list_voices_tool, 
                heygen_generate_video_tool, heygen_video_status_tool
            )
            globals()[name] = locals()[name]
            return locals()[name]
        except ImportError as e:
            logger.error(f"Failed to import {name}: {e}")
            raise
    
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")