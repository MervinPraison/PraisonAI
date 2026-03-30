"""HeyGen AI video generation tools.

HeyGen provides AI-powered avatar video generation capabilities.
This module requires the HEYGEN_API_KEY environment variable to be set.

Usage:
    from praisonaiagents.tools import heygen_list_avatars, heygen_generate_video
    
    # List available avatars
    avatars = heygen_list_avatars()
    
    # Generate a video
    result = heygen_generate_video("Hello world!", avatar_id="default")
    
    # Or use the class directly
    from praisonaiagents.tools import HeyGenTools
    heygen = HeyGenTools()
    avatars = heygen.list_avatars()
"""

from typing import Dict, Any, Optional, List
import logging
import os
import time


def _check_heygen_available() -> tuple[bool, Optional[str]]:
    """Check if HeyGen is available and API key is set.
    
    Returns:
        Tuple of (is_available, error_message)
    """
    # Check if requests package is available
    try:
        import requests
    except ImportError:
        return False, "requests package is not installed. Please install it using: pip install requests"
    
    # Check if API key is set
    api_key = os.environ.get("HEYGEN_API_KEY")
    if not api_key:
        return False, "HEYGEN_API_KEY environment variable is not set. Please set it to use HeyGen tools."
    
    return True, None


class HeyGenTools:
    """Comprehensive tools for AI avatar video generation using HeyGen API.
    
    HeyGen provides photorealistic talking-head avatar video generation from text scripts.
    
    Features:
    - List available avatars and voices
    - Generate AI avatar videos from text scripts
    - Check video generation status and get download URLs
    - Support for Avatar IV model (photorealistic quality)
    
    Requires:
    - requests package: pip install requests
    - HEYGEN_API_KEY environment variable
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize HeyGenTools.
        
        Args:
            api_key: Optional API key. If not provided, uses HEYGEN_API_KEY env var.
        """
        self._api_key = api_key
        self._base_url = "https://api.heygen.com"
    
    def _get_api_key(self) -> Optional[str]:
        """Get API key from instance or environment."""
        return self._api_key or os.environ.get("HEYGEN_API_KEY")
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for HeyGen API requests."""
        api_key = self._get_api_key()
        if not api_key:
            raise ValueError("HEYGEN_API_KEY not set")
        
        return {
            "x-api-key": api_key,
            "Content-Type": "application/json"
        }
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request to HeyGen API with error handling."""
        is_available, error = _check_heygen_available()
        if not is_available:
            logging.error(error)
            return {"error": error}
        
        import requests
        
        try:
            url = f"{self._base_url}{endpoint}"
            headers = self._get_headers()
            
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                timeout=30,
                **kwargs
            )
            
            # HeyGen API returns JSON responses
            try:
                result = response.json()
            except ValueError:
                result = {"text": response.text}
            
            if response.status_code != 200:
                error_msg = f"HeyGen API error (status {response.status_code}): {result.get('message', result.get('error', 'Unknown error'))}"
                logging.error(error_msg)
                return {"error": error_msg}
            
            return result
            
        except requests.exceptions.RequestException as e:
            error_msg = f"HeyGen request error: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}
        except Exception as e:
            error_msg = f"HeyGen unexpected error: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}
    
    def list_avatars(self) -> Dict[str, Any]:
        """List available HeyGen avatars.
        
        Returns:
            Dict containing:
            - avatars: List of avatar objects with id, name, gender, etc.
            - error: Error message if request failed
        """
        return self._make_request("GET", "/v2/avatars")
    
    def list_voices(self) -> Dict[str, Any]:
        """List available HeyGen voices.
        
        Returns:
            Dict containing:
            - voices: List of voice objects with id, name, language, gender, etc.
            - error: Error message if request failed
        """
        return self._make_request("GET", "/v2/voices")
    
    def generate_video(
        self,
        script: str,
        avatar_id: str = "default",
        voice_id: str = "default",
        title: str = "Generated Video",
        width: int = 1920,
        height: int = 1080,
        use_avatar_iv_model: bool = True,
        callback_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate an AI avatar video from a text script.
        
        Args:
            script: Text script for the avatar to speak (max 5000 chars)
            avatar_id: ID of the avatar to use
            voice_id: ID of the voice to use
            title: Title for the video
            width: Video width in pixels
            height: Video height in pixels
            use_avatar_iv_model: Use Avatar IV for photorealistic quality (uses more credits)
            callback_url: Optional webhook URL for completion notification
            
        Returns:
            Dict containing:
            - video_id: ID to track video generation status
            - message: Success message
            - error: Error message if request failed
        """
        if len(script) > 5000:
            return {"error": "Script length exceeds 5000 character limit"}
        
        payload = {
            "title": title,
            "video_inputs": [
                {
                    "character": {
                        "type": "avatar",
                        "avatar_id": avatar_id
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
        
        if use_avatar_iv_model:
            payload["video_inputs"][0]["character"]["use_avatar_iv_model"] = True
        
        if callback_url:
            payload["callback_url"] = callback_url
        
        return self._make_request("POST", "/v2/video/generate", json=payload)
    
    def video_status(self, video_id: str) -> Dict[str, Any]:
        """Check the status of a video generation and get download URL when ready.
        
        Args:
            video_id: The video ID returned from generate_video
            
        Returns:
            Dict containing:
            - status: Video status ("processing", "completed", "failed", etc.)
            - video_url: Download URL when status is "completed"
            - duration: Video duration in seconds when completed
            - error: Error message if request failed
        """
        return self._make_request("GET", f"/v1/video_status.get?video_id={video_id}")


# Standalone functions for direct import and @tool decorator usage

def heygen_list_avatars() -> Dict[str, Any]:
    """List available HeyGen avatars with their IDs.
    
    Returns available avatars for video generation including their IDs,
    names, gender, and other metadata.
    
    Returns:
        Dict with avatars list or error message
    """
    tools = HeyGenTools()
    return tools.list_avatars()


def heygen_list_voices() -> Dict[str, Any]:
    """List available HeyGen voices with their IDs.
    
    Returns available voices for video generation including their IDs,
    names, languages, and other metadata.
    
    Returns:
        Dict with voices list or error message
    """
    tools = HeyGenTools()
    return tools.list_voices()


def heygen_generate_video(
    script: str,
    avatar_id: str = "default",
    voice_id: str = "default",
    title: str = "Generated Video",
    width: int = 1920,
    height: int = 1080,
    use_avatar_iv_model: bool = True,
    callback_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate an AI avatar video from a text script using HeyGen.
    
    Creates a photorealistic talking-head avatar video from the provided
    text script. Returns immediately with a video_id for status tracking.
    
    Args:
        script: Text script for the avatar to speak (max 5000 chars)
        avatar_id: ID of the avatar to use (get from heygen_list_avatars)
        voice_id: ID of the voice to use (get from heygen_list_voices) 
        title: Title for the video
        width: Video width in pixels
        height: Video height in pixels
        use_avatar_iv_model: Use Avatar IV for photorealistic quality (uses ~6 credits/min vs ~1 credit/min)
        callback_url: Optional webhook URL for completion notification
        
    Returns:
        Dict with video_id for tracking or error message
    """
    tools = HeyGenTools()
    return tools.generate_video(
        script=script,
        avatar_id=avatar_id,
        voice_id=voice_id,
        title=title,
        width=width,
        height=height,
        use_avatar_iv_model=use_avatar_iv_model,
        callback_url=callback_url,
    )


def heygen_video_status(video_id: str) -> Dict[str, Any]:
    """Check the status of a HeyGen video generation and return download URL when ready.
    
    Polls the HeyGen API to check if video generation is complete.
    When status is "completed", includes the download URL.
    
    Args:
        video_id: The video ID returned from heygen_generate_video
        
    Returns:
        Dict with status, video_url (when ready), duration, or error message
    """
    tools = HeyGenTools()
    return tools.video_status(video_id)


def heygen_wait_for_completion(
    video_id: str,
    max_wait_seconds: int = 300,
    poll_interval: int = 10,
) -> Dict[str, Any]:
    """Wait for HeyGen video generation to complete and return the result.
    
    Convenience function that polls video_status until completion or timeout.
    
    Args:
        video_id: The video ID returned from heygen_generate_video
        max_wait_seconds: Maximum time to wait in seconds (default: 5 minutes)
        poll_interval: How often to check status in seconds (default: 10 seconds)
        
    Returns:
        Dict with final status and video_url when completed, or error/timeout
    """
    tools = HeyGenTools()
    start_time = time.time()
    
    while time.time() - start_time < max_wait_seconds:
        result = tools.video_status(video_id)
        
        if "error" in result:
            return result
        
        status = result.get("status", "").lower()
        if status == "completed":
            return result
        elif status == "failed":
            return {"error": f"Video generation failed: {result.get('error_message', 'Unknown error')}"}
        
        time.sleep(poll_interval)
    
    return {"error": f"Video generation timed out after {max_wait_seconds} seconds"}


if __name__ == "__main__":
    # Example usage
    print("\n" + "="*50)
    print("HeyGen Tools Demonstration")
    print("="*50 + "\n")
    
    # Check if API key is available
    is_available, error = _check_heygen_available()
    if not is_available:
        print(f"Error: {error}")
        print("\nTo use HeyGen tools:")
        print("1. Install: pip install requests")
        print("2. Set environment variable: export HEYGEN_API_KEY=your_api_key")
    else:
        print("HeyGen is available!")
        
        # Example: List avatars
        print("\n1. List Avatars")
        print("-" * 30)
        avatars_result = heygen_list_avatars()
        if "error" not in avatars_result:
            avatars = avatars_result.get("avatars", [])
            print(f"Found {len(avatars)} avatars")
            for avatar in avatars[:3]:  # Show first 3
                print(f"  - {avatar.get('name', 'Unknown')}: {avatar.get('avatar_id', 'No ID')}")
        else:
            print(f"Error: {avatars_result['error']}")
        
        # Example: List voices  
        print("\n2. List Voices")
        print("-" * 30)
        voices_result = heygen_list_voices()
        if "error" not in voices_result:
            voices = voices_result.get("voices", [])
            print(f"Found {len(voices)} voices")
            for voice in voices[:3]:  # Show first 3
                print(f"  - {voice.get('name', 'Unknown')}: {voice.get('voice_id', 'No ID')}")
        else:
            print(f"Error: {voices_result['error']}")
        
        # Example: Generate video (commented out to avoid using credits)
        print("\n3. Generate Video (Example - not executed)")
        print("-" * 45)
        print("video_result = heygen_generate_video(")
        print("    script='Hello, this is a demo of PraisonAI with HeyGen!',")
        print("    title='PraisonAI Demo Video'")
        print(")")
        print("# Returns: {'video_id': 'xyz123', 'message': 'Video generation started'}")
        
        print("\n" + "="*50)
        print("Demonstration Complete")
        print("="*50)


# Alias for simple usage: from praisonaiagents.tools import heygen
heygen = heygen_generate_video