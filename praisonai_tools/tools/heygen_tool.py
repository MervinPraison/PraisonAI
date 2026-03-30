"""HeyGen AI video generation tool for PraisonAI agents.

HeyGen is the leading AI video platform for generating photorealistic talking-head avatar videos from text scripts.

Usage:
    from praisonai_tools import heygen_generate_video, heygen_list_avatars
    from praisonaiagents import Agent
    
    agent = Agent(
        name="Video Creator",
        instructions="You create professional AI avatar videos using HeyGen.",
        tools=[heygen_list_avatars, heygen_generate_video, heygen_video_status]
    )
    
    result = agent.start("Create a 30-second explainer video about PraisonAI")

Environment Variables:
    HEYGEN_API_KEY: Required API key from HeyGen dashboard Settings > API
"""

from typing import Dict, List, Optional, Any
import os
import time
import logging

logger = logging.getLogger(__name__)

# Lazy imports inside functions to avoid module-level overhead
def _get_requests():
    """Lazy import of requests library."""
    try:
        import requests
        return requests
    except ImportError:
        raise ImportError(
            "requests library is required for HeyGen tool. "
            "Install with: pip install requests"
        )


class HeyGenTool:
    """HeyGen AI video generation tool class.
    
    Provides methods for interacting with the HeyGen API to generate AI avatar videos.
    Follows the existing tool pattern for PraisonAI.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize HeyGen tool.
        
        Args:
            api_key: HeyGen API key. If not provided, will use HEYGEN_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("HEYGEN_API_KEY")
        if not self.api_key:
            raise ValueError(
                "HeyGen API key is required. Set HEYGEN_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        self.base_url = "https://api.heygen.com"
        self.headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json"
        }
    
    def list_avatars(self) -> List[Dict[str, Any]]:
        """List available HeyGen avatars with their IDs.
        
        Returns:
            List of avatar dictionaries containing id, name, and other metadata
            
        Raises:
            Exception: If API request fails
        """
        requests = _get_requests()
        
        try:
            response = requests.get(
                f"{self.base_url}/v2/avatars",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            avatars = data.get("data", {}).get("avatars", [])
            
            logger.info(f"Retrieved {len(avatars)} avatars from HeyGen")
            return avatars
            
        except Exception as e:
            logger.error(f"Failed to list HeyGen avatars: {e}")
            raise Exception(f"Failed to list HeyGen avatars: {e}")
    
    def list_voices(self) -> List[Dict[str, Any]]:
        """List available HeyGen voices with their IDs.
        
        Returns:
            List of voice dictionaries containing id, name, language, and other metadata
            
        Raises:
            Exception: If API request fails
        """
        requests = _get_requests()
        
        try:
            response = requests.get(
                f"{self.base_url}/v2/voices",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            voices = data.get("data", {}).get("voices", [])
            
            logger.info(f"Retrieved {len(voices)} voices from HeyGen")
            return voices
            
        except Exception as e:
            logger.error(f"Failed to list HeyGen voices: {e}")
            raise Exception(f"Failed to list HeyGen voices: {e}")
    
    def generate_video(
        self,
        script: str,
        avatar_id: str = "default",
        voice_id: str = "default", 
        title: str = "Generated Video",
        width: int = 1920,
        height: int = 1080,
        use_avatar_iv: bool = True,
        callback_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate an AI avatar video from a text script using HeyGen.
        
        Args:
            script: Text script for the avatar to speak (max 5000 characters)
            avatar_id: ID of the avatar to use (get from list_avatars)
            voice_id: ID of the voice to use (get from list_voices)  
            title: Title for the generated video
            width: Video width in pixels
            height: Video height in pixels
            use_avatar_iv: Whether to use Avatar IV model for photorealistic quality
            callback_url: Optional webhook URL for completion notification
            
        Returns:
            Dictionary containing video_id and other metadata
            
        Raises:
            Exception: If API request fails or script is too long
        """
        if len(script) > 5000:
            raise ValueError("Script must be 5000 characters or less")
            
        requests = _get_requests()
        
        payload = {
            "title": title,
            "video_inputs": [
                {
                    "character": {
                        "type": "avatar",
                        "avatar_id": avatar_id,
                        "scale": 1.0
                    },
                    "voice": {
                        "type": "text_to_speech",
                        "voice_id": voice_id,
                        "input_text": script
                    }
                }
            ],
            "dimension": {
                "width": width,
                "height": height
            }
        }
        
        if use_avatar_iv:
            payload["use_avatar_iv_model"] = True
            
        if callback_url:
            payload["callback_url"] = callback_url
        
        try:
            response = requests.post(
                f"{self.base_url}/v2/video/generate",
                json=payload,
                headers=self.headers,
                timeout=60
            )
            response.raise_for_status()
            
            data = response.json()
            video_id = data.get("data", {}).get("video_id")
            
            if not video_id:
                raise Exception("No video_id returned from HeyGen API")
                
            logger.info(f"Video generation started: {video_id}")
            return {
                "video_id": video_id,
                "status": "processing",
                "title": title,
                "created_at": time.time()
            }
            
        except Exception as e:
            logger.error(f"Failed to generate HeyGen video: {e}")
            raise Exception(f"Failed to generate HeyGen video: {e}")
    
    def video_status(self, video_id: str) -> Dict[str, Any]:
        """Check the status of a HeyGen video generation and return download URL when ready.
        
        Args:
            video_id: The video ID returned from generate_video
            
        Returns:
            Dictionary containing status, download URL (when completed), and other metadata
            
        Raises:
            Exception: If API request fails
        """
        requests = _get_requests()
        
        try:
            response = requests.get(
                f"{self.base_url}/v1/video_status.get?video_id={video_id}",
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            status_data = data.get("data", {})
            
            result = {
                "video_id": video_id,
                "status": status_data.get("status", "unknown"),
                "progress": status_data.get("progress", 0),
                "duration": status_data.get("duration"),
                "created_at": status_data.get("created_at"),
                "updated_at": status_data.get("updated_at")
            }
            
            # Add download URL if completed
            if result["status"] == "completed":
                result["download_url"] = status_data.get("video_url")
                result["thumbnail_url"] = status_data.get("thumbnail_url")
                
            logger.info(f"Video {video_id} status: {result['status']}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to get video status for {video_id}: {e}")
            raise Exception(f"Failed to get video status: {e}")


# Tool function implementations using @tool decorator pattern
def heygen_list_avatars() -> List[Dict[str, Any]]:
    """List available HeyGen avatars with their IDs.
    
    Returns:
        List of avatar dictionaries with id, name, and metadata
        
    Example:
        avatars = heygen_list_avatars()
        for avatar in avatars:
            print(f"Avatar: {avatar['name']} (ID: {avatar['id']})")
    """
    tool = HeyGenTool()
    return tool.list_avatars()


def heygen_list_voices() -> List[Dict[str, Any]]:
    """List available HeyGen voices with their IDs.
    
    Returns:
        List of voice dictionaries with id, name, language, and metadata
        
    Example:
        voices = heygen_list_voices()
        for voice in voices:
            print(f"Voice: {voice['name']} - {voice['language']} (ID: {voice['id']})")
    """
    tool = HeyGenTool()
    return tool.list_voices()


def heygen_generate_video(
    script: str,
    avatar_id: str = "default",
    voice_id: str = "default",
    title: str = "Generated Video",
    width: int = 1920,
    height: int = 1080
) -> Dict[str, Any]:
    """Generate an AI avatar video from a text script using HeyGen.
    
    This is an async operation - use heygen_video_status() to check progress.
    
    Args:
        script: Text script for the avatar to speak (max 5000 chars)
        avatar_id: Avatar ID from heygen_list_avatars() (default uses HeyGen default)
        voice_id: Voice ID from heygen_list_voices() (default uses HeyGen default)  
        title: Title for the generated video
        width: Video width in pixels (default 1920)
        height: Video height in pixels (default 1080)
        
    Returns:
        Dictionary with video_id to track generation progress
        
    Example:
        result = heygen_generate_video(
            script="Hello, this is generated by HeyGen API.",
            avatar_id="your_avatar_id",
            voice_id="your_voice_id", 
            title="My AI Video"
        )
        video_id = result["video_id"]
        
        # Check status later
        status = heygen_video_status(video_id)
    """
    tool = HeyGenTool()
    return tool.generate_video(
        script=script,
        avatar_id=avatar_id, 
        voice_id=voice_id,
        title=title,
        width=width,
        height=height
    )


def heygen_video_status(video_id: str) -> Dict[str, Any]:
    """Check the status of a HeyGen video generation and return download URL when ready.
    
    Args:
        video_id: Video ID from heygen_generate_video()
        
    Returns:
        Dictionary with status, progress, and download_url (when completed)
        
    Status values:
        - "processing": Video is being generated
        - "completed": Video is ready, download_url available
        - "failed": Generation failed
        
    Example:
        status = heygen_video_status("your_video_id")
        if status["status"] == "completed":
            print(f"Video ready: {status['download_url']}")
        elif status["status"] == "processing":
            print(f"Progress: {status['progress']}%")
    """
    tool = HeyGenTool()
    return tool.video_status(video_id)


# For backwards compatibility and class-based usage
__all__ = [
    "HeyGenTool",
    "heygen_list_avatars",
    "heygen_list_voices", 
    "heygen_generate_video",
    "heygen_video_status"
]