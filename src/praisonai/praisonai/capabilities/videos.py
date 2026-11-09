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


def _build_call_kwargs(
    model: str,
    prompt: str,
    duration: Optional[int],
    aspect_ratio: Optional[str],
    timeout: float,
    kwargs: Dict[str, Any],
) -> Dict[str, Any]:
    """Build litellm.video_generation kwargs without unset or non-spec fields.

    LiteLLM's video providers read ``seconds`` and ``size`` (OpenAI Videos API
    names). Unknown keys such as ``duration`` are forwarded verbatim, and
    strict OpenAI-compatible servers reject the request when they are
    present. Map ``duration`` to ``seconds`` and drop anything left unset.
    """
    call_kwargs: Dict[str, Any] = {
        'model': model,
        'prompt': prompt,
        'timeout': timeout,
    }
    if duration is not None and 'seconds' not in kwargs:
        call_kwargs['seconds'] = str(duration)
    if aspect_ratio is not None:
        call_kwargs['aspect_ratio'] = aspect_ratio
    call_kwargs.update(kwargs)
    return call_kwargs


def video_generate(
    prompt: str,
    model: str = "openai/sora-2",
    duration: Optional[int] = None,
    aspect_ratio: Optional[str] = None,
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
        model: Model name (e.g., "openai/sora-2")
        duration: Video duration in seconds. Sent as ``seconds`` (the OpenAI
            Videos API field) unless ``seconds`` is passed explicitly.
            Omitted when None, so the provider default applies.
        aspect_ratio: Aspect ratio (e.g., "16:9", "9:16", "1:1"). Only
            forwarded when set; OpenAI-style providers take ``size`` instead.
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
    
    call_kwargs = _build_call_kwargs(model, prompt, duration, aspect_ratio, timeout, kwargs)
    
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
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
    model: str = "openai/sora-2",
    duration: Optional[int] = None,
    aspect_ratio: Optional[str] = None,
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
    
    call_kwargs = _build_call_kwargs(model, prompt, duration, aspect_ratio, timeout, kwargs)
    
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
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
