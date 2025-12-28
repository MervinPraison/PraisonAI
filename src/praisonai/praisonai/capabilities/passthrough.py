"""
Passthrough Capabilities Module

Provides generic API passthrough functionality for provider-specific endpoints.
"""

from dataclasses import dataclass, field
from typing import Optional, Any, Dict


@dataclass
class PassthroughResult:
    """Result from passthrough API call."""
    data: Any
    status_code: int = 200
    headers: Optional[Dict[str, str]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def passthrough(
    endpoint: str,
    method: str = "POST",
    model: Optional[str] = None,
    custom_llm_provider: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> PassthroughResult:
    """
    Make a passthrough API call to a provider endpoint.
    
    Args:
        endpoint: The endpoint path (e.g., "/v1/custom/endpoint")
        method: HTTP method ("GET", "POST", "PUT", "DELETE")
        model: Optional model name for routing
        custom_llm_provider: Provider name
        data: Form data
        json_data: JSON body data
        headers: Additional headers
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        metadata: Optional metadata for tracing
        
    Returns:
        PassthroughResult with response data
        
    Example:
        >>> result = passthrough(
        ...     "/v1/custom/endpoint",
        ...     method="POST",
        ...     json_data={"key": "value"},
        ...     custom_llm_provider="openai"
        ... )
        >>> print(result.data)
    """
    import litellm
    
    call_kwargs = {
        'endpoint': endpoint,
        'method': method,
        'timeout': timeout,
    }
    
    if model:
        call_kwargs['model'] = model
    if custom_llm_provider:
        call_kwargs['custom_llm_provider'] = custom_llm_provider
    if data:
        call_kwargs['data'] = data
    if json_data:
        call_kwargs['json'] = json_data
    if headers:
        call_kwargs['request_headers'] = headers
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    if metadata:
        call_kwargs['metadata'] = metadata
    
    # Use passthrough route if available
    try:
        response = litellm.llm_passthrough_route(**call_kwargs)
        
        return PassthroughResult(
            data=response.json() if hasattr(response, 'json') else response,
            status_code=getattr(response, 'status_code', 200),
            headers=dict(response.headers) if hasattr(response, 'headers') else None,
            metadata=metadata or {},
        )
    except AttributeError:
        # Fallback to httpx if passthrough not available
        import httpx
        
        url = f"{api_base or 'https://api.openai.com'}{endpoint}"
        request_headers = headers or {}
        if api_key:
            request_headers['Authorization'] = f"Bearer {api_key}"
        
        with httpx.Client(timeout=timeout) as client:
            response = client.request(
                method=method,
                url=url,
                headers=request_headers,
                json=json_data,
                data=data,
            )
        
        return PassthroughResult(
            data=response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text,
            status_code=response.status_code,
            headers=dict(response.headers),
            metadata=metadata or {},
        )


async def apassthrough(
    endpoint: str,
    method: str = "POST",
    model: Optional[str] = None,
    custom_llm_provider: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> PassthroughResult:
    """
    Async: Make a passthrough API call to a provider endpoint.
    
    See passthrough() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'endpoint': endpoint,
        'method': method,
        'timeout': timeout,
    }
    
    if model:
        call_kwargs['model'] = model
    if custom_llm_provider:
        call_kwargs['custom_llm_provider'] = custom_llm_provider
    if data:
        call_kwargs['data'] = data
    if json_data:
        call_kwargs['json'] = json_data
    if headers:
        call_kwargs['request_headers'] = headers
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    if metadata:
        call_kwargs['metadata'] = metadata
    
    try:
        response = await litellm.allm_passthrough_route(**call_kwargs)
        
        return PassthroughResult(
            data=response.json() if hasattr(response, 'json') else response,
            status_code=getattr(response, 'status_code', 200),
            headers=dict(response.headers) if hasattr(response, 'headers') else None,
            metadata=metadata or {},
        )
    except AttributeError:
        import httpx
        
        url = f"{api_base or 'https://api.openai.com'}{endpoint}"
        request_headers = headers or {}
        if api_key:
            request_headers['Authorization'] = f"Bearer {api_key}"
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=request_headers,
                json=json_data,
                data=data,
            )
        
        return PassthroughResult(
            data=response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text,
            status_code=response.status_code,
            headers=dict(response.headers),
            metadata=metadata or {},
        )
