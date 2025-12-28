"""
OCR Capabilities Module

Provides optical character recognition functionality via LiteLLM.
"""

from dataclasses import dataclass, field
from typing import Optional, Union, List, Any, Dict


@dataclass
class OCRResult:
    """Result from OCR processing."""
    text: str
    pages: Optional[List[Dict[str, Any]]] = None
    model: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def ocr(
    document: Union[str, Dict[str, str]],
    model: str = "mistral/mistral-ocr-latest",
    include_image_base64: bool = False,
    pages: Optional[List[int]] = None,
    image_limit: Optional[int] = None,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> OCRResult:
    """
    Extract text from documents or images using OCR.
    
    Args:
        document: Document URL, file path, or dict with type and URL
            - String: treated as URL or file path
            - Dict: {"type": "document_url", "document_url": "https://..."} or
                   {"type": "image_url", "image_url": "https://..."}
        model: Model name (e.g., "mistral/mistral-ocr-latest")
        include_image_base64: Whether to include base64 images in response
        pages: Specific pages to process (for PDFs)
        image_limit: Maximum number of images to process
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        metadata: Optional metadata for tracing
        
    Returns:
        OCRResult with extracted text
        
    Example:
        >>> result = ocr("https://example.com/document.pdf")
        >>> print(result.text)
        
        >>> result = ocr({"type": "image_url", "image_url": "https://example.com/image.png"})
    """
    import litellm
    
    # Handle document input
    doc_input = document
    if isinstance(document, str):
        # Check if it's a URL or file path
        if document.startswith(('http://', 'https://')):
            if document.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                doc_input = {"type": "image_url", "image_url": document}
            else:
                doc_input = {"type": "document_url", "document_url": document}
        else:
            # Local file - read and encode as base64
            import base64
            with open(document, 'rb') as f:
                content = base64.b64encode(f.read()).decode('utf-8')
            if document.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                doc_input = {"type": "image_url", "image_url": f"data:image/png;base64,{content}"}
            else:
                doc_input = {"type": "document_url", "document_url": f"data:application/pdf;base64,{content}"}
    
    call_kwargs = {
        'model': model,
        'document': doc_input,
        'timeout': timeout,
    }
    
    if include_image_base64:
        call_kwargs['include_image_base64'] = include_image_base64
    if pages:
        call_kwargs['pages'] = pages
    if image_limit:
        call_kwargs['image_limit'] = image_limit
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    if metadata:
        call_kwargs['metadata'] = metadata
    
    response = litellm.ocr(**call_kwargs)
    
    # Extract text from pages
    text_parts = []
    pages_data = []
    if hasattr(response, 'pages'):
        for page in response.pages:
            page_text = getattr(page, 'markdown', '') or getattr(page, 'text', '')
            text_parts.append(page_text)
            pages_data.append({
                'index': getattr(page, 'index', 0),
                'markdown': getattr(page, 'markdown', ''),
                'images': getattr(page, 'images', []),
            })
    
    usage = None
    if hasattr(response, 'usage_info'):
        usage = {
            'pages_processed': getattr(response.usage_info, 'pages_processed', 0),
            'doc_size_bytes': getattr(response.usage_info, 'doc_size_bytes', 0),
        }
    
    return OCRResult(
        text='\n\n'.join(text_parts),
        pages=pages_data if pages_data else None,
        model=model,
        usage=usage,
        metadata=metadata or {},
    )


async def aocr(
    document: Union[str, Dict[str, str]],
    model: str = "mistral/mistral-ocr-latest",
    include_image_base64: bool = False,
    pages: Optional[List[int]] = None,
    image_limit: Optional[int] = None,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> OCRResult:
    """
    Async: Extract text from documents or images using OCR.
    
    See ocr() for full documentation.
    """
    import litellm
    
    doc_input = document
    if isinstance(document, str):
        if document.startswith(('http://', 'https://')):
            if document.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                doc_input = {"type": "image_url", "image_url": document}
            else:
                doc_input = {"type": "document_url", "document_url": document}
        else:
            import base64
            with open(document, 'rb') as f:
                content = base64.b64encode(f.read()).decode('utf-8')
            if document.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                doc_input = {"type": "image_url", "image_url": f"data:image/png;base64,{content}"}
            else:
                doc_input = {"type": "document_url", "document_url": f"data:application/pdf;base64,{content}"}
    
    call_kwargs = {
        'model': model,
        'document': doc_input,
        'timeout': timeout,
    }
    
    if include_image_base64:
        call_kwargs['include_image_base64'] = include_image_base64
    if pages:
        call_kwargs['pages'] = pages
    if image_limit:
        call_kwargs['image_limit'] = image_limit
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    if metadata:
        call_kwargs['metadata'] = metadata
    
    response = await litellm.aocr(**call_kwargs)
    
    text_parts = []
    pages_data = []
    if hasattr(response, 'pages'):
        for page in response.pages:
            page_text = getattr(page, 'markdown', '') or getattr(page, 'text', '')
            text_parts.append(page_text)
            pages_data.append({
                'index': getattr(page, 'index', 0),
                'markdown': getattr(page, 'markdown', ''),
                'images': getattr(page, 'images', []),
            })
    
    usage = None
    if hasattr(response, 'usage_info'):
        usage = {
            'pages_processed': getattr(response.usage_info, 'pages_processed', 0),
            'doc_size_bytes': getattr(response.usage_info, 'doc_size_bytes', 0),
        }
    
    return OCRResult(
        text='\n\n'.join(text_parts),
        pages=pages_data if pages_data else None,
        model=model,
        usage=usage,
        metadata=metadata or {},
    )
