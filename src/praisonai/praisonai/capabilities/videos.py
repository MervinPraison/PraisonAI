"""
Videos Capabilities Module

Provides video generation functionality via LiteLLM.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Any, Dict


@dataclass
class VideoResult:
    """Result from video generation."""
    url: Optional[str] = None
    id: Optional[str] = None
    status: Optional[str] = None
    model: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def video_generate(
    prompt: str,
    model: str = "runway/gen3a_turbo",
    duration: int = 5,
    aspect_ratio: str = "16:9",
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> VideoResult:
    """
    Generate a video from a text prompt.
    
    Args:
        prompt: Text description of the video to generate
        model: Model name (e.g., "runway/gen3a_turbo")
        duration: Video duration in seconds
        aspect_ratio: Aspect ratio (e.g., "16:9", "9:16", "1:1")
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        metadata: Optional metadata for tracing
        
    Returns:
        VideoResult with video URL or ID
        
    Example:
        >>> result = video_generate("A sunset over the ocean")
        >>> print(result.url)
    """
    import litellm
    
    call_kwargs = {
        'model': model,
        'prompt': prompt,
        'duration': duration,
        'aspect_ratio': aspect_ratio,
        'timeout': timeout,
    }
    
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    if metadata:
        call_kwargs['metadata'] = metadata
    
    # Try to use video generation if available
    try:
        response = litellm.video_generation(**call_kwargs)
        
        return VideoResult(
            url=getattr(response, 'url', None),
            id=getattr(response, 'id', None),
            status=getattr(response, 'status', 'completed'),
            model=model,
            metadata=metadata or {},
        )
    except AttributeError:
        # Fallback if video_generation not available
        raise NotImplementedError(
            "Video generation is not yet fully supported. "
            "Please check LiteLLM documentation for available video models."
        )


async def avideo_generate(
    prompt: str,
    model: str = "runway/gen3a_turbo",
    duration: int = 5,
    aspect_ratio: str = "16:9",
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> VideoResult:
    """
    Async: Generate a video from a text prompt.
    
    See video_generate() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'model': model,
        'prompt': prompt,
        'duration': duration,
        'aspect_ratio': aspect_ratio,
        'timeout': timeout,
    }
    
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    if metadata:
        call_kwargs['metadata'] = metadata
    
    try:
        response = await litellm.avideo_generation(**call_kwargs)
        
        return VideoResult(
            url=getattr(response, 'url', None),
            id=getattr(response, 'id', None),
            status=getattr(response, 'status', 'completed'),
            model=model,
            metadata=metadata or {},
        )
    except AttributeError:
        raise NotImplementedError(
            "Video generation is not yet fully supported. "
            "Please check LiteLLM documentation for available video models."
        )
