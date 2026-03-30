"""Decorator versions of tools for direct agent use.

This module provides @tool decorated versions of the HeyGen tools that can be 
directly imported and used with PraisonAI agents.

Usage:
    from praisonai_tools.decorators import heygen_generate_video_tool, heygen_list_avatars_tool
    from praisonaiagents import Agent
    
    agent = Agent(
        name="Video Creator", 
        tools=[heygen_list_avatars_tool, heygen_generate_video_tool]
    )
"""

from typing import List, Dict, Any

# Lazy import of @tool decorator
def _get_tool_decorator():
    """Lazy import of @tool decorator from praisonaiagents."""
    try:
        from praisonaiagents import tool
        return tool
    except ImportError:
        raise ImportError(
            "@tool decorator requires praisonaiagents. "
            "Install with: pip install praisonaiagents"
        )


def create_heygen_tools():
    """Create @tool decorated versions of HeyGen tools.
    
    Returns:
        Tuple of (list_avatars_tool, list_voices_tool, generate_video_tool, video_status_tool)
    """
    from .tools.heygen_tool import heygen_list_avatars, heygen_list_voices, heygen_generate_video, heygen_video_status
    
    tool = _get_tool_decorator()
    
    @tool
    def heygen_list_avatars_tool() -> List[Dict[str, Any]]:
        """List available HeyGen avatars with their IDs."""
        return heygen_list_avatars()
    
    @tool 
    def heygen_list_voices_tool() -> List[Dict[str, Any]]:
        """List available HeyGen voices with their IDs."""
        return heygen_list_voices()
    
    @tool
    def heygen_generate_video_tool(
        script: str,
        avatar_id: str = "default",
        voice_id: str = "default", 
        title: str = "Generated Video"
    ) -> Dict[str, Any]:
        """Generate an AI avatar video from a text script using HeyGen.
        
        Args:
            script: Text script for the avatar to speak (max 5000 chars)
            avatar_id: Avatar ID from heygen_list_avatars() 
            voice_id: Voice ID from heygen_list_voices()
            title: Title for the generated video
            
        Returns:
            Dictionary with video_id to track generation progress
        """
        return heygen_generate_video(script, avatar_id, voice_id, title)
    
    @tool
    def heygen_video_status_tool(video_id: str) -> Dict[str, Any]:
        """Check the status of a HeyGen video generation.
        
        Args:
            video_id: Video ID from heygen_generate_video()
            
        Returns:
            Dictionary with status, progress, and download_url (when completed)
        """
        return heygen_video_status(video_id)
    
    return (
        heygen_list_avatars_tool,
        heygen_list_voices_tool, 
        heygen_generate_video_tool,
        heygen_video_status_tool
    )


# Pre-create the tools for direct import
try:
    (
        heygen_list_avatars_tool,
        heygen_list_voices_tool,
        heygen_generate_video_tool, 
        heygen_video_status_tool
    ) = create_heygen_tools()
    
    __all__ = [
        "heygen_list_avatars_tool",
        "heygen_list_voices_tool",
        "heygen_generate_video_tool",
        "heygen_video_status_tool",
        "create_heygen_tools"
    ]
    
except ImportError:
    # praisonaiagents not available, tools will be created when imported
    __all__ = ["create_heygen_tools"]