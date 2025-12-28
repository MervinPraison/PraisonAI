"""
Images Capabilities Module

Provides image generation and editing functionality via LiteLLM.
"""

from dataclasses import dataclass, field
from typing import Optional, Union, List, Any, Dict


@dataclass
class ImageResult:
    """Result from image generation or editing."""
    url: Optional[str] = None
    b64_json: Optional[str] = None
    revised_prompt: Optional[str] = None
    model: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def save(self, path: str) -> str:
        """Save image to file (from base64 or download from URL)."""
        if self.b64_json:
            import base64
            with open(path, 'wb') as f:
                f.write(base64.b64decode(self.b64_json))
        elif self.url:
            import urllib.request
            urllib.request.urlretrieve(self.url, path)
        else:
            raise ValueError("No image data available")
        return path


def image_generate(
    prompt: str,
    model: str = "dall-e-3",
    n: int = 1,
    size: str = "1024x1024",
    quality: str = "standard",
    style: Optional[str] = None,
    response_format: str = "url",
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> List[ImageResult]:
    """
    Generate images from a text prompt using LiteLLM.
    
    Args:
        prompt: Text description of the image to generate
        model: Model name (e.g., "dall-e-3", "dall-e-2", "stability/...")
        n: Number of images to generate
        size: Image size (e.g., "1024x1024", "1792x1024", "1024x1792")
        quality: Image quality ("standard" or "hd")
        style: Image style ("vivid" or "natural")
        response_format: "url" or "b64_json"
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        metadata: Optional metadata for tracing
        
    Returns:
        List of ImageResult objects
        
    Example:
        >>> results = image_generate("A sunset over mountains")
        >>> results[0].save("sunset.png")
    """
    import litellm
    
    call_kwargs = {
        'model': model,
        'prompt': prompt,
        'n': n,
        'size': size,
        'response_format': response_format,
        'timeout': timeout,
    }
    
    # Only add quality/style for dall-e-3 (not supported by dall-e-2)
    if 'dall-e-3' in model.lower():
        call_kwargs['quality'] = quality
        if style:
            call_kwargs['style'] = style
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    if metadata:
        call_kwargs['metadata'] = metadata
    
    response = litellm.image_generation(**call_kwargs)
    
    results = []
    if hasattr(response, 'data'):
        for item in response.data:
            results.append(ImageResult(
                url=getattr(item, 'url', None),
                b64_json=getattr(item, 'b64_json', None),
                revised_prompt=getattr(item, 'revised_prompt', None),
                model=model,
                metadata=metadata or {},
            ))
    
    return results


async def aimage_generate(
    prompt: str,
    model: str = "dall-e-3",
    n: int = 1,
    size: str = "1024x1024",
    quality: str = "standard",
    style: Optional[str] = None,
    response_format: str = "url",
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> List[ImageResult]:
    """
    Async: Generate images from a text prompt using LiteLLM.
    
    See image_generate() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'model': model,
        'prompt': prompt,
        'n': n,
        'size': size,
        'response_format': response_format,
        'timeout': timeout,
    }
    
    # Only add quality/style for dall-e-3 (not supported by dall-e-2)
    if 'dall-e-3' in model.lower():
        call_kwargs['quality'] = quality
        if style:
            call_kwargs['style'] = style
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    if metadata:
        call_kwargs['metadata'] = metadata
    
    response = await litellm.aimage_generation(**call_kwargs)
    
    results = []
    if hasattr(response, 'data'):
        for item in response.data:
            results.append(ImageResult(
                url=getattr(item, 'url', None),
                b64_json=getattr(item, 'b64_json', None),
                revised_prompt=getattr(item, 'revised_prompt', None),
                model=model,
                metadata=metadata or {},
            ))
    
    return results


def image_edit(
    image: Union[str, bytes],
    prompt: str,
    model: str = "dall-e-2",
    mask: Optional[Union[str, bytes]] = None,
    n: int = 1,
    size: str = "1024x1024",
    response_format: str = "url",
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> List[ImageResult]:
    """
    Edit an image using a text prompt.
    
    Args:
        image: Path to image file or image bytes
        prompt: Text description of the edit
        model: Model name
        mask: Optional mask image (transparent areas will be edited)
        n: Number of images to generate
        size: Output image size
        response_format: "url" or "b64_json"
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        metadata: Optional metadata for tracing
        
    Returns:
        List of ImageResult objects
    """
    import litellm
    
    # Handle file paths
    image_file = image
    if isinstance(image, str):
        image_file = open(image, 'rb')
    
    mask_file = mask
    if mask and isinstance(mask, str):
        mask_file = open(mask, 'rb')
    
    try:
        call_kwargs = {
            'model': model,
            'image': image_file,
            'prompt': prompt,
            'n': n,
            'size': size,
            'response_format': response_format,
            'timeout': timeout,
        }
        
        if mask_file:
            call_kwargs['mask'] = mask_file
        if api_key:
            call_kwargs['api_key'] = api_key
        if api_base:
            call_kwargs['api_base'] = api_base
        
        call_kwargs.update(kwargs)
        
        if metadata:
            call_kwargs['metadata'] = metadata
        
        response = litellm.image_edit(**call_kwargs)
        
        results = []
        if hasattr(response, 'data'):
            for item in response.data:
                results.append(ImageResult(
                    url=getattr(item, 'url', None),
                    b64_json=getattr(item, 'b64_json', None),
                    model=model,
                    metadata=metadata or {},
                ))
        
        return results
    finally:
        if isinstance(image, str) and hasattr(image_file, 'close'):
            image_file.close()
        if mask and isinstance(mask, str) and hasattr(mask_file, 'close'):
            mask_file.close()


async def aimage_edit(
    image: Union[str, bytes],
    prompt: str,
    model: str = "dall-e-2",
    mask: Optional[Union[str, bytes]] = None,
    n: int = 1,
    size: str = "1024x1024",
    response_format: str = "url",
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> List[ImageResult]:
    """
    Async: Edit an image using a text prompt.
    
    See image_edit() for full documentation.
    """
    import litellm
    
    image_file = image
    if isinstance(image, str):
        image_file = open(image, 'rb')
    
    mask_file = mask
    if mask and isinstance(mask, str):
        mask_file = open(mask, 'rb')
    
    try:
        call_kwargs = {
            'model': model,
            'image': image_file,
            'prompt': prompt,
            'n': n,
            'size': size,
            'response_format': response_format,
            'timeout': timeout,
        }
        
        if mask_file:
            call_kwargs['mask'] = mask_file
        if api_key:
            call_kwargs['api_key'] = api_key
        if api_base:
            call_kwargs['api_base'] = api_base
        
        call_kwargs.update(kwargs)
        
        if metadata:
            call_kwargs['metadata'] = metadata
        
        response = await litellm.aimage_edit(**call_kwargs)
        
        results = []
        if hasattr(response, 'data'):
            for item in response.data:
                results.append(ImageResult(
                    url=getattr(item, 'url', None),
                    b64_json=getattr(item, 'b64_json', None),
                    model=model,
                    metadata=metadata or {},
                ))
        
        return results
    finally:
        if isinstance(image, str) and hasattr(image_file, 'close'):
            image_file.close()
        if mask and isinstance(mask, str) and hasattr(mask_file, 'close'):
            mask_file.close()
